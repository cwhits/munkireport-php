#!/usr/bin/python
"""Script for updating MunkiReport"""
import os
import datetime
import subprocess
import json
import urllib
import urllib2
import shutil
import tarfile
import argparse
from distutils.version import LooseVersion
from distutils.dir_util import copy_tree

NOW = datetime.datetime.now()

class MunkiReportInstall(object):
    """A MunkiReport Install."""
    def __init__(self, install_path):
        self._install_path = os.path.join(install_path,'') or self.install_path
        self._env = self.env_vars
        self._database_type = self.database_type

    @property
    def install_path(self):
        """Return install path"""
        return os.path.dirname(os.path.realpath(__file__)).strip('build')
    
    @property
    def build_version(self):
        """Return build version"""
        helper = self._install_path + "app/helpers/site_helper.php"
        if os.path.exists(helper):
            with open(helper, "r") as site_helper:
                for line in site_helper:
                    # There is probably a more pythonic way of doing this...
                    if "$GLOBALS['version'] = '" in line:
                        return line.split("'")[3]
        return None

    @property
    def database_type(self):
        """Return database type"""
        if self._env is not None:
            return self._env['CONNECTION_DRIVER'].strip('"') or 'sqlite'
        return None

    @property
    def install_type(self):
        """Return zip or git install type"""
        if os.path.exists(self._install_path + '.git'):
            return 'git'
        return 'zip'

    @property
    def env_vars(self):
        """Return env vars"""
        env_file_path = self._install_path + '.env'
        if os.path.isfile(env_file_path):
            env_vars = {}
            with open(env_file_path) as env_file:
                for line in env_file:
                    if line.startswith('#') or not line.strip():
                        continue
                    key, value = line.strip().split('=', 1)
                    env_vars[key] = value.strip('"')
            return env_vars
        else:
            return None

    def set_maintenance_mode(self, value):
        """Set maintenance mode to down or remove"""
        if value == "down":
            open(self._install_path + 'storage/framework/' + value, 'a').close()
        else:
            os.remove(self._install_path + 'storage/framework/down')

    def backup_database(self):
        """Backup a MunkiReport database."""
        if self._database_type == "mysql":
            username = self._env['CONNECTION_USERNAME']
            password = self._env['CONNECTION_PASSWORD']
            database = self._env['CONNECTION_DATABASE']
            backup_file = BACKUP_DIR + database + NOW.strftime("%Y%m%d%H%M") + '.bak'
            cmd = "/usr/local/opt/mysql-client/bin/mysqldump" \
                  " --user={} --password={} {} > {}".format(
                      username, password, database, backup_file
                  )
            print "Backing up database to {}".format(backup_file)
            #subprocess.Popen(cmd, shell=True)
        elif self._database_type == 'sqlite':
            shutil.copyfile(
                self.install_path + 'app/db/db.sqlite',
                BACKUP_DIR + 'db' + NOW.strftime("%Y%m%d%H%M") + '.sqlite.bak'
            )

    def backup_files(self, install_path, install_type):
        """Create file backup of install."""
        if install_type == 'git':
            final_dir = BACKUP_DIR + "munkireport" + NOW.strftime("%Y%m%d%H%M")
            print "Backing up files to {}".format(final_dir)
            os.mkdir(final_dir)
            copy_tree(install_path, final_dir)
        elif install_type == 'zip':
            final_dir = BACKUP_DIR + "munkireport" + NOW.strftime("%Y%m%d%H%M")
            os.mkdir(final_dir)
            copy_tree(install_path, final_dir)

def github_release_info():
    """Return MR API data"""
    mr_api = "https://api.github.com/repos/munkireport/munkireport-php/releases/latest"
    response = urllib.urlopen(mr_api)
    data = json.loads(response.read())
    # print data['tarball_url']
    return data

def main(info, no_backup, backup_dir, install_path, upgrade, upgrade_version):
    """Main script"""
    munkireport = MunkiReportInstall(install_path)
    install_path = install_path or munkireport.install_path
    install_type = munkireport.install_type
    build_version = munkireport.build_version
    release_info = github_release_info()

    if not build_version:
        print(
                'The directory, {}, does not appear'
                ' to be a valid MunkiReport install'
                ).format(install_path)
        return

    if info:
        print("Current version: {}").format(build_version)
        print("GitHub version:  {}").format(release_info['tag_name'].strip('v'))
        print("Install path:    {}").format(install_path)
        print("Install type:    {}").format(install_type)
        print("Database type:   {}").format(munkireport.database_type)
        return

    print("We are at version {}. The latest master version is {}".format(
        build_version,
        release_info['tag_name'].strip('v')
    ))

    if build_version < release_info['tag_name'].strip('v'):
        print("Starting upgrade of {}".format(install_path))
        return
        munkireport.set_maintenance_mode("down")

        # backup database
        munkireport.backup_database(install_path)

        # backup files
        munkireport.backup_files(install_path, install_type)

        # Update

        if munkireport.install_type == 'git':
            try:
                # do git pull
                print "Starting git pull"
                process = subprocess.Popen(["git", "pull"], stdout=subprocess.PIPE)
                output = process.communicate()[0]
                print "Finishing git pull"
                print "Running composer"
                os.chdir(munkireport.install_path)
                process = subprocess.Popen(["/usr/local/bin/composer", "update", "--no-dev"],
                                           stdout=subprocess.PIPE)
                output = process.communicate()[0]
                print "Composer finished"
                os.chdir(munkireport.install_path + "/build/")
            except:
                print "Git stuff fail."
        elif munkireport.install_type == 'zip':
            # download new munkireport
            if (LooseVersion(munkireport.build_version) >
                    LooseVersion(release_info['tag_name'].strip('v'))):
                print "Local version is newer than the latest master release."
            elif LooseVersion(munkireport.build_version) < LooseVersion("4.0.0"):
                print "Local version is older than 4.0.0"
            else:
                print "Downloading the latest release"
                extracted_location = "/tmp/extracted"
                filedata = urllib2.urlopen(release_info['tarball_url'])
                datatowrite = filedata.read()
                with open('/tmp/munkireport_latest.tar.gz', 'wb') as mr_download:
                    mr_download.write(datatowrite)
                # remove the old directory
                shutil.rmtree(extracted_location)
                try:
                    os.makedirs(extracted_location)
                except:
                    print "Directory already exists"
                tar = tarfile.open("/tmp/munkireport_latest.tar.gz")
                tar.extractall(extracted_location)
                tar.close()

        # Run Migrations
        print "Running migrations"
        migration_file = munkireport.install_path + 'database/migrate.php'
        cmd = "/usr/bin/php %s" % migration_file
        print cmd
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
        migration_response = proc.stdout.read()
        print "Finished migrations"

        # turn off maintenance mode
        munkireport.set_maintenance_mode("up")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
            description='Manage a MunkiReport install.')
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
            '-i', '--info',
            action='store_true',
            help='Print info on the MunkiReport install.'
            )
    parser.add_argument(
            '--no-backup',
            help='Do not take any backups before upgrading.',
            default=False
            )
    parser.add_argument(
            '--backup-dir',
            help='Directory to back up to.',
            default='/tmp'
            )
    parser.add_argument(
            '--install-path',
            help='Install path for MunkiReport.',
            default=os.path.dirname(os.path.realpath(__file__)).strip('build')
            )
    parser.add_argument(
            '--upgrade',
            help='Attempt to upgrade MunkiReport',
            default='False'
            )
    parser.add_argument(
            '--upgrade-version',
            help='Version of MunkiReport to upgrade to.',
            default='latest'
            )
    args = parser.parse_args()
    main(
            args.info,
            args.no_backup,
            args.backup_dir,
            args.install_path,
            args.upgrade,
            args.upgrade_version
        )
