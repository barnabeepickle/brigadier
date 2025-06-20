import os,sys,subprocess,re,tempfile,shutil,optparse,datetime,platform,plistlib,json

from xml.dom import minidom
import downloader

if 2/3==0: input = raw_input # type: ignore

# SUCATALOG_URL = 'http://swscan.apple.com/content/catalogs/others/index-10.11-10.10-10.9-mountainlion-lion-snowleopard-leopard.merged-1.sucatalog'
SUCATALOG_URL = 'https://swscan.apple.com/content/catalogs/others/index-10.14-10.13-10.12-10.11-10.10-10.9-mountainlion-lion-snowleopard-leopard.merged-1.sucatalog'
if os.name=="nt": # Set Windows-specific properties
    z_json = "https://sourceforge.net/projects/sevenzip/best_release.json"
    z_url2 = "https://www.7-zip.org/a/7z1806-x64.msi"
    z_url  = "https://www.7-zip.org/a/7z[[vers]]-x64.msi"
    z_name = "7z.exe"
    z_path = None
    z_path64 = os.path.join(os.environ['SYSTEMDRIVE'] + "\\", "Program Files", "7-Zip", "7z.exe")
    z_path32 = os.path.join(os.environ['SYSTEMDRIVE'] + "\\", "Program Files (x86)", "7-Zip", "7z.exe")

d = downloader.Downloader()

def status(msg):
    print("{}\n".format(msg))

def getCommandOutput(cmd):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    out, err = p.communicate()
    return out

def load_plist(fp):
    if sys.version_info >= (3,0):
        return plistlib.load(fp)
    else:
        return plistlib.readPlist(fp)

def loads_plist(s):
    if sys.version_info >= (3,0):
        return plistlib.loads(s)
    else:
        return plistlib.readPlistFromString(s)

def check_7z():
    global z_path
    z_path = next((x for x in (z_path64,z_path32) if os.path.exists(x)),None)
    if z_path: return True
    print("Couldn't locate {} - downloading...".format(z_name))
    # Didn't find it - let's do some stupid stuff
    # First we get our json response - or rather, try to, then parse it
    # looking for the current version
    dl_url = None
    try:
        json_data = json.loads(d.get_string(z_json,progress=False))
        v_num = json_data.get("release",{}).get("filename","").split("/")[-1].lower().split("-")[0].replace("7z","").replace(".exe","")
        if len(v_num):
            dl_url = z_url.replace("[[vers]]",v_num)
    except:
        pass
    if not dl_url: # Fall back on a known-good version
        dl_url = z_url2
    temp = tempfile.mkdtemp()
    dl_name = os.path.basename(dl_url)
    dl_file = d.stream_to_file(dl_url, os.path.join(temp, dl_name))
    print("") # Move to the next line to avoid overwriting
    print(dl_file)
    if not dl_file: # Didn't download right
        shutil.rmtree(temp,ignore_errors=True)
        return False
    print("")
    print("Installing 7zip...")
    retcode = subprocess.call(['msiexec', '/qn', '/i', os.path.join(temp, dl_name)])
    if retcode != 0:
        print("{} returned an error code of {} - trying to run in interactive mode...".format(dl_name,retcode))
        retcode = subprocess.call(['msiexec', '/i', os.path.join(temp, dl_name)])
        if retcode != 0:
            shutil.rmtree(temp,ignore_errors=True)
            print("Error ({})".format(retcode))
            exit(1)
    print("")
    z_path = next((x for x in (z_path64,z_path32) if os.path.exists(x)),None)
    return z_path and os.path.exists(z_path)

# Returns this machine's model identifier, using wmic on Windows,
# system_profiler on OS X
def getMachineModel():
    if platform.system() == 'Windows':
        wmic = os.path.join(os.environ['SYSTEMDRIVE'] + "\\", "Windows", "System32", "wbem", "WMIC.exe")
        rawxml = getCommandOutput([wmic, 'computersystem', 'get', 'model', '/format:RAWXML'])
        dom = minidom.parseString(rawxml)
        results = dom.getElementsByTagName("RESULTS")
        nodes = results[0].getElementsByTagName("CIM")[0].getElementsByTagName("INSTANCE")[0]\
        .getElementsByTagName("PROPERTY")[0].getElementsByTagName("VALUE")[0].childNodes
        model = nodes[0].data
    elif platform.system() == 'Darwin':
        plistxml = getCommandOutput(['system_profiler', 'SPHardwareDataType', '-xml'])
        plist = loads_plist(plistxml)
        model = plist[0]['_items'][0]['machine_model']
    return model

def sevenzipExtract(arcfile, command='e', out_dir=None):
    if not z_path and not check_7z(): exit(1) # Yikes - shouldn't happen
    cmd = [z_path]
    cmd.append(command)
    if not out_dir:
        out_dir = os.path.dirname(arcfile)
    cmd.append("-o" + out_dir)
    cmd.append("-y")
    cmd.append(arcfile)
    status("Calling 7-Zip command: {}".format(' '.join(cmd)))
    retcode = subprocess.call(cmd)
    if retcode:
        sys.exit("Command failure: {} exited {}.".format(' '.join(cmd), retcode))

def postInstallConfig():
    regdata = """Windows Registry Editor Version 5.00

[HKEY_CURRENT_USER\\Software\\Apple Inc.\\Apple Keyboard Support]
"FirstTimeRun"=dword:00000000"""
    handle, path = tempfile.mkstemp()
    fd = os.fdopen(handle, 'w')
    fd.write(regdata)
    fd.close()
    subprocess.call(['regedit.exe', '/s', path])

def findBootcampMSI(search_dir):
    """Returns the path of the 64-bit BootCamp MSI"""
    # Most ESDs contain 'BootCamp.msi' and 'BootCamp64.msi'
    # Dec. 2012 ESD contains only 'BootCamp.msi' which is 64-bit
    # The top-level structure of the ESD files depends on whether
    # it's an AutoUnattend-based ESD as well, ie:
    # /Drivers/Apple/BootCamp64.msi, or
    # /BootCamp/Drivers/Apple/BootCamp.msi
    candidates = ['BootCamp64.msi', 'BootCamp.msi']
    for root, dirs, files in os.walk(search_dir):
        for msi in candidates:
            if msi in files:
                return os.path.join(root, msi)

def installBootcamp(msipath):
    logpath = os.path.abspath("/BootCamp_Install.log")
    cmd = ['cmd', '/c', 'msiexec', '/i', msipath, '/qb-', '/norestart', '/log', logpath]
    status("Executing command: '{}'".format(" ".join(cmd)))
    subprocess.call(cmd)
    status("Install log output:")
    with open(logpath, 'r') as logfd:
        logdata = logfd.read()
        print(logdata.decode('utf-16'))
    postInstallConfig()
    
def main():
    scriptdir = os.path.abspath(os.path.dirname(sys.argv[0]))

    o = optparse.OptionParser()
    o.add_option('-m', '--model', action="append",
        help="System model identifier to use (otherwise this machine's \
model is used). This can be specified multiple times to download \
multiple models in a single run.")
    o.add_option('-i', '--install', action="store_true",
        help="After the installer is downloaded, perform the install automatically. \
Can be used on Windows only.")
    o.add_option('-o', '--output-dir',
        help="Base path where the installer files will be extracted into a folder named after the \
product, ie. 'BootCamp-041-1234'. Uses the current directory if this option is omitted.")
    o.add_option('-k', '--keep-files', action="store_true",
        help="Keep the files that were downloaded/extracted. Useful only with the \
'--install' option on Windows.")
    o.add_option('-p', '--product-id',
        help="Specify an exact product ID to download (ie. '031-0787'), currently useful only for cases \
where a model has multiple BootCamp ESDs available and is not downloading the desired version \
according to the post date.")
    o.add_option('-l', '--latest-version', action="store_true",
        help="Gets whichever version is latest. This overrides model and product-id if specified.")

    opts, args = o.parse_args()
    if opts.install:
        if platform.system() == 'Darwin':
            sys.exit("Installing Boot Camp can only be done on Windows!")
        if platform.system() == 'Windows' and platform.machine() != 'AMD64':
            sys.exit("Installing on anything other than 64-bit Windows is currently not supported!")

    if opts.output_dir:
        if not os.path.isdir(opts.output_dir):
            sys.exit("Output directory {} that was specified doesn't exist!".format(opts.output_dir))
        if not os.access(opts.output_dir, os.W_OK):
            sys.exit("Output directory {} is not writable by this user!".format(opts.output_dir))
        output_dir = opts.output_dir
    else:
        output_dir = os.getcwd()
        if output_dir.endswith('ystem32') or '\\system32\\' in output_dir.lower():
            output_dir = os.environ['SystemDrive'] + "\\"
            status("Changing output directory to {} to work around an issue when running the installer out of 'system32'.".format(output_dir))

    if opts.keep_files and not opts.install:
        sys.exit("The --keep-files option is only useful when used with --install option!")

    if opts.model:
        if opts.install:
            status("Ignoring '--model' when '--install' is used. The Boot Camp "
                   "installer won't allow other models to be installed, anyway.")
        if opts.latest_version:
            status("Ignoring '--model' when '--latest-version' is used. The Boot Camp "
                   "installer won't allow other models to be installed, anyway.")
        models = opts.model
    else:
        models = [getMachineModel()]
    if opts.latest_version:
        if opts.install:
            status("Ignoring '--latest-version' when '--install' is used. The Boot Camp "
                   "installer won't allow other models to be installed, anyway.")
            opts.latest_version = False
        else:
            models = ["All"]
    if len(models) > 1:
        status("Using Mac models: {}.".format(', '.join(models)))
    else:
        status("Using Mac model: {}.".format(', '.join(models)))        

    for model in models:
        sucatalog_url = SUCATALOG_URL
        # check if we defined anything in brigadier.plist
        config_plist = None
        plist_path = os.path.join(scriptdir, 'brigadier.plist')
        if os.path.isfile(plist_path):
            try:
                with open(plist_path, "rb") as f:
                    config_plist = load_plist(f)
            except:
                status("Config plist was found at {} but it could not be read. \
                Verify that it is readable and is an XML formatted plist.".format(plist_path))
        if config_plist:
            if 'CatalogURL' in list(config_plist):
                sucatalog_url = config_plist['CatalogURL']


        data = d.get_bytes(sucatalog_url,progress=False)
        p = loads_plist(data)
        allprods = p['Products']

        # Get all Boot Camp ESD products
        bc_prods = []
        for (prod_id, prod_data) in allprods.items():
            if 'ServerMetadataURL' in list(prod_data):
                bc_match = re.search('BootCamp', prod_data['ServerMetadataURL'])
                if bc_match:
                    bc_prods.append((prod_id, prod_data))
        # Find the ESD(s) that applies to our model
        pkg_data = []
        re_model = r"([a-zA-Z]{4,12}[1-9]{1,2}\,[1-6])"
        for bc_prod in bc_prods:
            if 'English' in list(bc_prod[1]['Distributions']):
                disturl = bc_prod[1]['Distributions']['English']
                dist_data = d.get_string(disturl,progress=False)
                if opts.latest_version or re.search(model, dist_data):
                    supported_models = []
                    pkg_data.append({bc_prod[0]: bc_prod[1]})
                    model_matches_in_dist = re.findall(re_model, dist_data)
                    for supported_model in model_matches_in_dist:
                        supported_models.append(supported_model)
                    status("Model supported in package distribution file at {}.".format(disturl))
                    status("Distribution {} supports the following models: {}.".format(
                        bc_prod[0], ", ".join(supported_models)))
        
        # Ensure we have only one ESD
        if len(pkg_data) == 0:
            sys.exit("Couldn't find a Boot Camp ESD for the model {} in the given software update catalog.".format(model))
        if len(pkg_data) == 1:
            pkg_data = pkg_data[0]
            if opts.product_id:
                sys.exit("--product-id option is only applicable when multiple ESDs are found for a model.")
        if len(pkg_data) > 1:
            # sys.exit("There is more than one ESD product available for this model: {}. "
            #          "Automically selecting the one with the most recent PostDate.." 
            #         .format(", ".join([list(p)[0] for p in pkg_data]))
            print("There is more than one ESD product available for this model:")
            # Init latest to be epoch start
            latest_date = datetime.datetime.fromtimestamp(0)
            chosen_product = None
            for i, p in enumerate(pkg_data):
                product = list(p)[0]
                postdate = p[product].get('PostDate')
                print("{}: PostDate {}".format(product, postdate))
                if postdate > latest_date:
                    latest_date = postdate
                    chosen_product = product

            if opts.product_id:
                if opts.product_id not in [list(k)[0] for k in pkg_data]:
                    sys.exit("Product specified with '--product-id {}' either doesn't exist "
                             "or was not found applicable to models: {}"
                            .format(opts.product_id, ", ".join(models)))
                chosen_product = opts.product_id
                print("Selecting manually-chosen product {}.".format(chosen_product))
            else:
                print("Selecting {} as it's the most recently posted.".format(chosen_product))

            for p in pkg_data:
                if list(p)[0] == chosen_product:
                    selected_pkg = p
            pkg_data = selected_pkg

        pkg_id = list(pkg_data)[0]
        pkg_url = pkg_data[pkg_id]['Packages'][0]['URL']

        # make a sub-dir in the output_dir here, named by product
        landing_dir = os.path.join(output_dir, 'BootCamp-' + pkg_id)
        if os.path.exists(landing_dir):
            status("Final output path {} already exists, removing it...".format(landing_dir))
            if platform.system() == 'Windows':
                # using rmdir /qs because shutil.rmtree dies on the Doc files with foreign language characters
                subprocess.call(['cmd', '/c', 'rmdir', '/q', '/s', landing_dir])
            else:
                shutil.rmtree(landing_dir)

        status("Making directory {}..".format(landing_dir))
        os.mkdir(landing_dir)

        arc_workdir = tempfile.mkdtemp(prefix="bootcamp-unpack_")
        pkg_dl_path = os.path.join(arc_workdir, pkg_url.split('/')[-1])

        status("Fetching Boot Camp product at URL {}.".format(pkg_url))
        d.stream_to_file(pkg_url, pkg_dl_path)
        print("") # Move to the next line to avoid overwriting

        if platform.system() == 'Windows':
            if not check_7z():
                print("7-Zip was not found - aborting...")
                exit(1)

            status("Extracting...")
            # BootCamp.pkg (xar) -> Payload (gzip) -> Payload~ (cpio) -> WindowsSupport.dmg
            for arc in [pkg_dl_path,
                        os.path.join(arc_workdir, 'Payload'),
                        os.path.join(arc_workdir, 'Payload~')]:
                if os.path.exists(arc):
                    sevenzipExtract(arc)
            # finally, 7-Zip also extracts the tree within the DMG to the output dir
            sevenzipExtract(os.path.join(arc_workdir, 'WindowsSupport.dmg'),
                            command='x',
                            out_dir=landing_dir)
            if opts.install:
                status("Installing Boot Camp...")
                installBootcamp(findBootcampMSI(landing_dir))
                if not opts.keep_files:
                    subprocess.call(['cmd', '/c', 'rmdir', '/q', '/s', landing_dir])

            # clean up the temp dir always
            subprocess.call(['cmd', '/c', 'rmdir', '/q', '/s', arc_workdir])


        elif platform.system() == 'Darwin':
            status("Expanding flat package...")
            subprocess.call(['/usr/sbin/pkgutil', '--expand', pkg_dl_path,
                            os.path.join(arc_workdir, 'pkg')])
            status("Extracting Payload...")
            subprocess.call(['/usr/bin/tar', '-xz', '-C', arc_workdir, '-f', os.path.join(arc_workdir, 'pkg', 'Payload')])
            output_file = os.path.join(landing_dir, 'WindowsSupport.dmg')
            shutil.move(os.path.join(arc_workdir, 'Library/Application Support/BootCamp/WindowsSupport.dmg'),
                output_file)
            status("Extracted to {}.".format(output_file))

            # If we were to also copy out the contents from the .dmg we might do it like this, but if you're doing this
            # from OS X you probably would rather just burn a disc so we'll stop here..
            # mountxml = getCommandOutput(['/usr/bin/hdiutil', 'attach',
            #     os.path.join(arc_workdir, 'Library/Application Support/BootCamp/WindowsSupport.dmg'),
            #     '-mountrandom', '/tmp', '-plist', '-nobrowse'])
            # mountplist = loads_plist(mountxml)
            # mntpoint = mountplist['system-entities'][0]['mount-point']
            # shutil.copytree(mntpoint, output_dir)
            # subprocess.call(['/usr/bin/hdiutil', 'eject', mntpoint])
            shutil.rmtree(arc_workdir)

    status("Done.")
    input("Press [enter] to exit...")
    sys.exit()

if __name__ == "__main__":
    main()
