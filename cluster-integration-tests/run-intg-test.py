# Copyright (c) 2018, WSO2 Inc. (http://wso2.com) All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# importing required modules
import sys
from xml.etree import ElementTree as ET
import subprocess
import wget
import logging
import inspect
import os
import shutil
import pymysql
import sqlparse
import stat
import re
import lxml.etree as XSET
from pathlib import Path
import urllib.request as urllib2
from xml.dom import minidom
from subprocess import Popen, PIPE
from const import TEST_PLAN_PROPERTY_FILE_NAME, INFRA_PROPERTY_FILE_NAME, LOG_FILE_NAME, DB_META_DATA, \
    PRODUCT_STORAGE_DIR_NAME, DEFAULT_DB_USERNAME, LOG_STORAGE, LOG_FILE_PATHS, DIST_POM_PATH, NS, ZIP_FILE_EXTENSION

git_repo_url = None
git_branch = None
workspace = None
dist_name = None
dist_zip_name = None
product_id = None
log_file_name = None
target_path = None
tag_name = None
product_version = None
database_config = {}
product_host = None
product_port = None
product_ip = None
test_mode = None

def read_proprty_files():
    global git_repo_url
    global git_branch
    global workspace
    global product_id
    global database_config
    global product_host
    global product_port
    global product_ip
    global test_mode

    workspace = os.getcwd()
    property_file_paths = []
    test_plan_prop_path = Path(workspace + "/" + TEST_PLAN_PROPERTY_FILE_NAME)
    infra_prop_path = Path(workspace + "/" + INFRA_PROPERTY_FILE_NAME)

    if Path.exists(test_plan_prop_path) and Path.exists(infra_prop_path):
        property_file_paths.append(test_plan_prop_path)
        property_file_paths.append(infra_prop_path)

        for path in property_file_paths:
            with open(path, 'r') as filehandle:
                for line in filehandle:
                    if line.startswith("#"):
                        continue
                    prop = line.split("=")
                    key = prop[0]
                    val = prop[1]
                    if key == "PRODUCT_GIT_URL":
                        git_repo_url = val.strip().replace('\\', '')
                        product_id = git_repo_url.split("/")[-1].split('.')[0]
                    elif key == "PRODUCT_GIT_BRANCH":
                        git_branch = val.strip()
                    elif key == "TEST_MODE":
                        test_mode = val.strip()
                    elif key == "PRODUCT_HOST":
                        product_host = val.strip()
                    elif key == "PRODUCT_PORT":
                        product_port = val.strip()
                    elif key == "PRODUCT_IP":
                        product_ip = val.strip()
    else:
        raise Exception("Test Plan Property file or Infra Property file is not in the workspace: " + workspace)


def validate_property_readings():
    missing_values = ""
    if git_repo_url is None:
        missing_values += " -PRODUCT_GIT_URL- "
    if product_id is None:
        missing_values += " -product-id- "
    if git_branch is None:
        missing_values += " -PRODUCT_GIT_BRANCH- "
    if product_host is None:
        missing_values += " -PRODUCT_HOST- "
    if product_port is None:
        missing_values += " -PRODUCT_PORT- "
    if product_ip is None:
        missing_values += " -PRODUCT_IP- "

    if missing_values != "":
        logger.error('Invalid property file is found. Missing values: %s ', missing_values)
        return False
    else:
        return True


def function_logger(file_level, console_level=None):
    global log_file_name
    log_file_name = LOG_FILE_NAME
    function_name = inspect.stack()[1][3]
    logger = logging.getLogger(function_name)
    # By default, logs all messages
    logger.setLevel(logging.DEBUG)

    if console_level != None:
        # StreamHandler logs to console
        ch = logging.StreamHandler()
        ch.setLevel(console_level)
        ch_format = logging.Formatter('%(asctime)s - %(message)s')
        ch.setFormatter(ch_format)
        logger.addHandler(ch)

    # log in to a file
    fh = logging.FileHandler("{0}.log".format(function_name))
    fh.setLevel(file_level)
    fh_format = logging.Formatter('%(asctime)s - %(lineno)d - %(levelname)-8s - %(message)s')
    fh.setFormatter(fh_format)
    logger.addHandler(fh)

    return logger


def download_file(url, destination):
    """Download a file using wget package.
    Download the given file in _url_ as the directory+name provided in _destination_
    """
    wget.download(url, destination)

def copy_file(source, target):
    """Copy the source file to the target.
    """
    shutil.copy(source, target)


def get_dist_name():
    """Get the product name by reading distribution pom.
    """
    global dist_name
    global dist_zip_name
    global product_version
    dist_pom_path = Path(workspace + "/" + product_id + "/" + DIST_POM_PATH[product_id])
    ET.register_namespace('', NS['d'])
    artifact_tree = ET.parse(dist_pom_path)
    artifact_root = artifact_tree.getroot()
    parent = artifact_root.find('d:parent', NS)
    artifact_id = artifact_root.find('d:artifactId', NS).text
    product_version = parent.find('d:version', NS).text
    dist_name = artifact_id + "-" + product_version
    dist_zip_name = dist_name + ZIP_FILE_EXTENSION
    return dist_name

def build_module(module_path):
    """Build a given module.
    """
    logger.info('Start building a module. Module: ' + str(module_path))
    if sys.platform.startswith('win'):
        subprocess.call(['mvn', 'clean', 'install', '-B',
                         '-Dorg.slf4j.simpleLogger.log.org.apache.maven.cli.transfer.Slf4jMavenTransferListener=warn'],
                        shell=True, cwd=module_path)
    else:
        subprocess.call(['mvn', 'clean', 'install', '-B',
                         '-Dorg.slf4j.simpleLogger.log.org.apache.maven.cli.transfer.Slf4jMavenTransferListener=warn'],
                        cwd=module_path)
    logger.info('Module build is completed. Module: ' + str(module_path))


def save_log_files():
    log_storage = Path(workspace + "/" + LOG_STORAGE)
    if not Path.exists(log_storage):
        Path(log_storage).mkdir(parents=True, exist_ok=True)
    log_file_paths = LOG_FILE_PATHS[product_id]
    if log_file_paths:
        for file in log_file_paths:
            absolute_file_path = Path(workspace + "/" + product_id + "/" + file)
            if Path.exists(absolute_file_path):
                copy_file(absolute_file_path, log_storage)
            else:
                logger.error("File doesn't contain in the given location: " + str(absolute_file_path))


def clone_repo():
    """Clone the product repo
    """
    try:
        subprocess.call(['git', 'clone', '--branch', git_branch, git_repo_url], cwd=workspace)
        logger.info('product repository cloning is done.')
    except Exception as e:
        logger.error("Error occurred while cloning the product repo: ", exc_info=True)


def checkout_to_tag(name):
    """Checkout to the given tag
    """
    try:
        git_path = Path(workspace + "/" + product_id)
        tag = "tags/" + name
        subprocess.call(["git", "fetch", "origin", tag], cwd=git_path)
        subprocess.call(["git", "checkout", "-B", tag, name], cwd=git_path)
        logger.info('checkout to the branch: ' + tag)
    except Exception as e:
        logger.error("Error occurred while cloning the product repo and checkout to the latest tag of the branch",
                     exc_info=True)


def get_latest_tag_name(product):
    """Get the latest tag name from git location
    """
    global tag_name
    git_path = Path(workspace + "/" + product)
    binary_val_of_tag_name = subprocess.Popen(["git", "describe", "--abbrev=0", "--tags"],
                                              stdout=subprocess.PIPE, cwd=git_path)
    tag_name = binary_val_of_tag_name.stdout.read().strip().decode("utf-8")
    return tag_name


def get_product_file_path():
    """Get the absolute path of the distribution which is located in the storage directory
    """
    # product download path and file name constructing
    product_download_dir = Path(workspace + "/" + PRODUCT_STORAGE_DIR_NAME)
    if not Path.exists(product_download_dir):
        Path(product_download_dir).mkdir(parents=True, exist_ok=True)
    return product_download_dir / dist_zip_name


def create_output_property_fle():
    """Create output property file which is used when generating email
    """
    output_property_file = open("output.properties", "w+")
    git_url = git_repo_url + "/tree/" + git_branch
    output_property_file.write("GIT_LOCATION=%s\r\n" % git_url)
    output_property_file.write("GIT_REVISION=%s\r\n" % tag_name)
    output_property_file.close()


def replace_file(source, destination):
    """Replace source file to the destination
    """
    logger.info('replacing files from:' + str(source) + "to: " + str(destination))
    shutil.move(source, destination)

def setPlatformTestHostConfig(file) :
    datafile=str(file)
    xmlparse = XSET.parse(datafile)
    xslt = XSET.parse(datafile)
    transform = XSET.XSLT(xslt)
    newdom = transform(xmlparse)
    root = newdom.getroot()
    
    PLATFORM_TEST_HOST_CONFIG = {   "xs:coverage/text()" : "true" ,
                                "xs:instance[@name='store']/xs:hosts/xs:host/text()" : product_host,
                                "xs:instance[@name='publisher']/xs:hosts/xs:host/text()" : product_host,
                                "xs:instance[@name='keyManager']/xs:hosts/xs:host/text()" : product_host,
                                "xs:instance[@name='gateway-mgt']/xs:hosts/xs:host/text()" : product_host,
                                "xs:instance[@name='gateway-wrk']/xs:hosts/xs:host/text()" : product_host,
				"xs:instance[@name='backend-server']/xs:hosts/xs:host/text()" : product_host,
                                "xs:instance/xs:ports/xs:port[@type='http']/text()" : "80",
                                "xs:instance/xs:ports/xs:port[@type='https']/text()" : "443",
                                "xs:instance/xs:ports/xs:port[@type='nhttp']/text()" : "8780",
                                "xs:instance/xs:ports/xs:port[@type='nhttps']/text()" : "8743"
                                }

    keysArray = PLATFORM_TEST_HOST_CONFIG.keys()
    print(keysArray)
    for key in keysArray:
        for conf in root.findall('{http://www.w3.org/1999/XSL/Transform}template'):
            if conf.attrib['match']==key:
                conf.text = PLATFORM_TEST_HOST_CONFIG.get(key)
    newdom.write(str(file))
    
    logger.info('Platform test host configurations successfully completed for: ' + str(file))

def build_module_param(module_path, mvn_param):
    """Build a given module for platform tests.
    """
    logger.info('Start building a module. Module: ' + str(module_path))
    subprocess.call(['mvn', 'clean', 'install', '-B',
                         '-Dorg.slf4j.simpleLogger.log.org.apache.maven.cli.transfer.Slf4jMavenTransferListener=warn', mvn_param],
                        cwd=module_path)
    logger.info('Platform module build is completed. Module: ' + str(module_path))

def cert_generation(product_host, product_port, cert_path):
    """Importing the cert to the test client.
    """
    cmd1 = "echo | openssl s_client -servername "+product_host+ " -connect "+product_host+":"+product_port+ " 2>/dev/null | openssl x509 -text > "+str(cert_path)+"/opensslcert.txt"
    cmd2 = "keytool -import -trustcacerts -alias testprod3 -file "+str(cert_path)+"/opensslcert.txt -keystore "+str(cert_path)+"/wso2carbon.jks -storepass wso2carbon -noprompt"
    cmd3 = "rm -rf "+str(cert_path)+"/opensslcert.txt"
    os.system(cmd1)
    os.system(cmd2)
    os.system(cmd3)
    logger.info('Product certificate imported successfully to the test client ')
    
def host_mapping(product_host, product_ip):
    if product_host not in open('/etc/hosts').read():
        cmd = "echo "+product_ip+" "+product_host+" >> /etc/hosts"
        os.system(cmd)
    else:
        logger.info('Hostname already defined')

def main():
    try:
        global logger
        global dist_name
        logger = function_logger(logging.DEBUG, logging.DEBUG)
        if sys.version_info < (3, 6):
            raise Exception(
                "To run run-intg-test.py script you must have Python 3.6 or latest. Current version info: " + sys.version_info)
        read_proprty_files()
        if not validate_property_readings():
            raise Exception(
                "Property file doesn't have mandatory key-value pair. Please verify the content of the property file "
                "and the format")
        # clone the repository
        clone_repo()

        if test_mode == "DEBUG":
            testng_source = Path(workspace + "/" + "testng.xml")
            testng_destination = Path(workspace + "/" + product_id + "/" +
                                      'modules/integration/tests-integration/tests-backend/src/test/resources/testng.xml')
            testng_server_mgt_source = Path(workspace + "/" + "testng-server-mgt.xml")
            testng_server_mgt_destination = Path(workspace + "/" + product_id + "/" +
                                                 'modules/integration/tests-integration/tests-backend/src/test/resources/testng-server-mgt.xml')
            # replace testng source
            replace_file(testng_source, testng_destination)
            # replace testng server mgt source
            replace_file(testng_server_mgt_source, testng_server_mgt_destination)
      
        host_mapping(product_host, product_ip)
        cert_path = Path(workspace + "/" + product_id + "/" +
                                      'modules/integration/tests-integration/tests-backend/src/test/resources/keystores/products')
        cert_generation(product_host,product_port,cert_path)
        if product_id == "product-apim":
            platform_template = Path(workspace + "/" + product_id + "/" +
                                      'modules/integration/tests-integration/tests-backend/src/test/resources/platform-test-host-config.xsl')
            setPlatformTestHostConfig(platform_template)
            module_path = Path(workspace + "/" + product_id + "/" + 'modules/api-import-export')
            build_module(module_path)
        intg_module_path = Path(workspace + "/" + product_id + "/" + 'modules/integration')
        build_module_param(intg_module_path, "-DplatformTests")
        save_log_files()
        create_output_property_fle()
    except Exception as e:
        logger.error("Error occurred while running the run-intg.py script", exc_info=True)
    except BaseException as e:
        logger.error("Error occurred while doing the configuration", exc_info=True)


if __name__ == "__main__":
    main()
