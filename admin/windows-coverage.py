#!/usr/bin/env python

# Wrapper for CTest to execute every test through OpenCPPCoverage.

# Unfortunately there doesn't seem to be way to hook into the process than
# pretending to be memory tester.

# Usage:

# cmake -DMEMORYCHECK_COMMAND=windows-coverage.py -DMEMORYCHECK_COMMAND_OPTIONS=--separator -DMEMORYCHECK_TYPE=Valgrind
# ctest -D NightlyMemCheck


import sys
import os
import xml.etree.ElementTree as ET
import re
import subprocess
import shutil


# The coverage merge code is based on
# https://github.com/x3mSpeedy/Flow123d-python-utils/blob/master/src/coverage/coverage_merge_module.py

# constants
PACKAGES_LIST = 'packages/package'
PACKAGES_ROOT = 'packages'
CLASSES_LIST = 'classes/class'
CLASSES_ROOT = 'classes'
METHODS_LIST = 'methods/method'
METHODS_ROOT = 'methods'
LINES_LIST = 'lines/line'
LINES_ROOT = 'lines'


class CoverageMerge (object):
    def __init__ (self, filename, xmlfiles):
        self.xmlfiles = xmlfiles
        self.finalxml = filename
        self.filteronly = False
        self.filtersuffix = ''
        self.packagefilters = None

    def execute_merge (self):
        # prepare filters
        self.prepare_packagefilters ()

        if self.filteronly:
            # filter all given files
            currfile = 1
            totalfiles = len (self.xmlfiles)
            for xmlfile in self.xmlfiles:
                xml = ET.parse (xmlfile)
                self.filter_xml (xml)
                xml.write (xmlfile + self.filtersuffix, encoding="UTF-8", xml_declaration=True)
                currfile += 1
        else:
            # merge all given files
            totalfiles = len (self.xmlfiles)

            # special case if only one file was given
            # filter given file and save it
            if (totalfiles == 1):
                xmlfile = self.xmlfiles.pop (0)
                xml = ET.parse (xmlfile)
                self.filter_xml (xml)
                xml.write (self.finalxml, encoding="UTF-8", xml_declaration=True)
                sys.exit (0)

            currfile = 1
            self.merge_xml (self.xmlfiles[0], self.xmlfiles[1], self.finalxml)

            currfile = 2
            for i in range (totalfiles - 2):
                xmlfile = self.xmlfiles[i + 2]
                self.merge_xml (self.finalxml, xmlfile, self.finalxml)
                currfile += 1

    def merge_xml (self, xmlfile1, xmlfile2, outputfile):
        # parse
        xml1 = ET.parse (xmlfile1)
        xml2 = ET.parse (xmlfile2)

        # get packages
        packages1 = self.filter_xml (xml1)
        packages2 = self.filter_xml (xml2)

        # find root
        packages1root = xml1.find (PACKAGES_ROOT)


        # merge packages
        self.merge (packages1root, packages1, packages2, 'name', self.merge_packages)

        # write result to output file
        xml1.write (outputfile, encoding="UTF-8", xml_declaration=True)


    def filter_xml (self, xmlfile):
        xmlroot = xmlfile.getroot ()
        packageroot = xmlfile.find (PACKAGES_ROOT)
        packages = xmlroot.findall (PACKAGES_LIST)

        # delete nodes from tree AND from list
        included = []
        for pckg in packages:
            name = pckg.get ('name')
            if not self.include_package (name):
                packageroot.remove (pckg)
            else:
                included.append (pckg)
        return included

    def prepare_packagefilters (self):
        if not self.packagefilters:
            return None

        # create simple regexp from given filter
        for i in range (len (self.packagefilters)):
            self.packagefilters[i] = '^' + self.packagefilters[i].replace ('.', '\.').replace ('*', '.*') + '$'

    def include_package (self, name):
        if not self.packagefilters:
            return True

        for packagefilter in self.packagefilters:
            if re.search (packagefilter, name):
                return True
        return False

    def get_attributes_chain (self, obj, attrs):
        """Return a joined arguments of object based on given arguments"""

        if type (attrs) is list:
            result = ''
            for attr in attrs:
                result += obj.attrib[attr]
            return result
        else:
            return obj.attrib[attrs]

    def merge (self, root, list1, list2, attr, merge_function):
        """ Groups given lists based on group attributes. Process of merging items with same key is handled by
            passed merge_function. Returns list1. """
        for item2 in list2:
            found = False
            for item1 in list1:
                if self.get_attributes_chain (item1, attr) == self.get_attributes_chain (item2, attr):
                    item1 = merge_function (item1, item2)
                    found = True
                    break
            if found:
                continue
            else:
                root.append (item2)

    def merge_packages (self, package1, package2):
        """Merges two packages. Returns package1."""
        classes1 = package1.findall (CLASSES_LIST)
        classes2 = package2.findall (CLASSES_LIST)
        if classes1 or classes2:
            self.merge (package1.find (CLASSES_ROOT), classes1, classes2, ['filename', 'name'], self.merge_classes)

        return package1

    def merge_classes (self, class1, class2):
        """Merges two classes. Returns class1."""

        lines1 = class1.findall (LINES_LIST)
        lines2 = class2.findall (LINES_LIST)
        if lines1 or lines2:
            self.merge (class1.find (LINES_ROOT), lines1, lines2, 'number', self.merge_lines)

        methods1 = class1.findall (METHODS_LIST)
        methods2 = class2.findall (METHODS_LIST)
        if methods1 or methods2:
            self.merge (class1.find (METHODS_ROOT), methods1, methods2, 'name', self.merge_methods)

        return class1

    def merge_methods (self, method1, method2):
        """Merges two methods. Returns method1."""

        lines1 = method1.findall (LINES_LIST)
        lines2 = method2.findall (LINES_LIST)
        self.merge (method1.find (LINES_ROOT), lines1, lines2, 'number', self.merge_lines)

    def merge_lines (self, line1, line2):
        """Merges two lines by summing their hits. Returns line1."""

        # merge hits
        value = int (line1.get ('hits')) + int (line2.get ('hits'))
        line1.set ('hits', str (value))

        # merge conditionals
        con1 = line1.get ('condition-coverage')
        con2 = line2.get ('condition-coverage')
        if con1 is not None and con2 is not None:
            con1value = int (con1.split ('%')[0])
            con2value = int (con2.split ('%')[0])
            # bigger coverage on second line, swap their conditionals
            if con2value > con1value:
                line1.set ('condition-coverage', str (con2))
                line1.__setitem__ (0, line2.__getitem__ (0))

        return line1


ROOT_DIR = 'c:/projects/gammu'
COVERAGE_XML = 'c:/projects/gammu/coverage.xml'
COVERAGE_TMP = 'coverage-tmp.xml'
COVERAGE_TMP_FULL = 'coverage-full.xml'
COVERAGE_CMD = ['OpenCppCoverage.exe', '--quiet', '--export_type', 'cobertura:coverage-tmp.xml', '--modules', ROOT_DIR, '--sources', ROOT_DIR, '--']


def main():
    for arg in sys.argv:
        if arg.startswith('--log-file='):
            filename = arg.split('=', 1)[1]
            # Create empty file
            open(filename, 'w')
            break
    command = sys.argv[sys.argv.index('--separator') + 1:]
    result = subprocess.call(COVERAGE_CMD + command)
    shutil.copy(COVERAGE_TMP, 'c:/projects/gammu/coverage-2.xml')
    if os.path.exists(COVERAGE_XML):
        # Merge coverage
        shutil.copy(COVERAGE_XML, COVERAGE_TMP_FULL)
        merger = CoverageMerge(COVERAGE_XML, [COVERAGE_TMP_FULL, COVERAGE_TMP]).execute_merge()
        os.remove(COVERAGE_TMP)
        os.remove(COVERAGE_TMP_FULL)
    else:
        # Initial coverage report
        shutil.move(COVERAGE_TMP, COVERAGE_XML)
    sys.exit(result)


if __name__ == '__main__':
    main()
