#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=C0321,C0103,C0301,E1101,C0303,E1004,C0330,R0915,R0914,W0703,C0326
# Disable many annoying pylint messages, warning me about variable naming for example.
# yes, in my code I'm caught between two worlds of snake_case and camelCase (transitioning to snake_case).

__author__      = "Neil R. Shapiro"
__copyright__   = "Copyright 2022, Psychoanalytic Electronic Publishing"
__license__     = "Apache 2.0"
__version__     = "2022.0628/v2.0.004"   # semver versioning after date.
__status__      = "Development"

programNameShort = "opasDataLoader"
XMLProcessingEnabled = True

import lxml
import sys
if sys.version_info[0] < 3:
    raise Exception("Must be using Python 3")

border = 80 * "*"
print (f"""\n
        {border}
            {programNameShort} - Open Publications-Archive Server (OPAS) Loader
                            Version {__version__}
                   Document/Authors/References Core Processor/Loader
        {border}
        """)

help_text = (
    fr""" 
        - Read the XML KBD3 files specified, process into EXP_ARCH in memory and load to Solr/RDS directly
        - Can also output and save EXP_ARCH (procesed files)
        - Can also load the database (Solr/RD) from EXP_ARCH1 files
        
        See documentation at:
          https://github.com/Psychoanalytic-Electronic-Publishing/OpenPubArchive-Content-Server/wiki/TBD  *** TBD ***
        
        Example Invocation:
                $ python opasDataLoader.py
                
        Important option choices:
         -h, --help         List all help options
         -a                 Force update of files (otherwise, only updated when the data is newer)
         --sub              Start with this subfolder of the root (can add sublevels to that)
         --key:             Do just one file with the specified PEP locator (e.g., --key AIM.076.0309A)
         --nocheck          Don't prompt whether to proceed after showing setting/option choices
         --reverse          Process in reverse
         --halfway          Stop after doing half of the files, so it can be run in both directions
         --whatsnewdays  Use the days back value supplied to write a new article log, rather than the specific files loaded.
                         Note that 1==today.
         --whatsnewfile  To specify the file in which to write the what's new list.
         --nofiles          Can be used in conjunction with whatsnewdays to simply produce the new article log rather than loading files.

         V.2 New Options (see default settings for many in loaderConfig.py)
         --inputbuild        input build name, e.g., (bKBD3) 
         --outputbuild       output build name, e.g., (bEXP_ARCH1) 
         --inputbuildpattern selection by build of what files to include
         --smartload         see if inputbuild file is newer or missing from db,
                             if so then compile and load, otherwise skip
         --prettyprint       Format generated XML (bEXP_ARCH1) nicely
         --nohelp            Turn off front-matter help (that displays when you run)
         --doctype           Output doctype (defaults to default_doctype setting in loaderConfig.py)
         
         We may not keep these...smartload should be enough:

         --load              mainly for backwards compatibility, it loads the EXP_ARCH1 files as
                             input files by default, skipping as before if not updated
         --compiletoload     Compiles KBD3 and loads (doesn't save bEXP_ARCH1 files)
         --compiletosave     Compiles KBD3 to bEXP_ARCH1 (rebuilds output files) but doesn't load DB
         --compiletorebuild  All encompassing...Compiles KBD3 to bEXP_ARCH1 and loads


        Example:
          Update all files from the root (default, pep-web-xml) down.  Starting two runs, one running the file list forward, the other backward.
          As long as you don't specify -a, they will skip the ones the other did when they eventually
          cross

             python opasDataLoader.py 
             python opasDataLoader.py --reverse

          Update all of PEPCurrent

             python opasDataLoader2.py -a --sub _PEPCurrent
             
          Generate a new articles log file for 10 days back
             
             python opasDataLoader.py --nofiles --whatsnewdays=10

          Import single precompiled file (e.g., EXP_ARCH1) only (no processing), verbose

             python opasDataLoader.py --verbose --key CFP.012.0022A --load --inputbuild=(bEXP_ARCH1)

          Import folder of precompiled files, even if the same (--rebuild).
             python opasDataLoader.py --verbose --sub _PEPCurrent\CFP\012.2022 --load --rebuild --inputbuild=(bEXP_ARCH1)
             
          Smart build folder of uncompiled XML files (e.g., bKBD3) if needed.
             python opasDataLoader.py --verbose --sub _PEPCurrent\CFP\012.2022 --smartload
                 

        Note:
          S3 is set up with root pep-web-xml (default).  The root must be the bucket name.
          
          S3 has subfolders _PEPArchive, _PEPCurrent, _PEPFree, _PEPOffsite
            to allow easy processing of one archive type at a time simply using
            the --sub option (or four concurrently for faster processing).
    """
)

import sys
sys.path.append('../libs')
sys.path.append('../config')
sys.path.append('../libs/configLib')

import time
import random
import pysolr
import localsecrets
import re
import os
import os.path
import pathlib
from opasFileSupport import FileInfo

import datetime as dtime
from datetime import datetime
import logging
logger = logging.getLogger(programNameShort)

from optparse import OptionParser

from lxml import etree
import mysql.connector

import configLib.opasCoreConfig
from configLib.opasCoreConfig import solr_authors2, solr_gloss2
import loaderConfig
import opasSolrLoadSupport

import opasXMLHelper as opasxmllib
import opasCentralDBLib
import opasProductLib
import opasFileSupport
import opasAPISupportLib

#detect data is on *nix or windows system
if "AWS" in localsecrets.CONFIG or re.search("/", localsecrets.IMAGE_SOURCE_PATH) is not None:
    path_separator = "/"
else:
    path_separator = r"\\"

# for processxml (build XML or update directly without intermediate file)
import opasXMLProcessor

# Module Globals
bib_total_reference_count = 0

def get_defaults(options, default_input_build_pattern, default_input_build):

    if options.input_build is not None:
        selected_input_build = options.input_build
    else:
        selected_input_build = default_input_build
        
    if options.input_build_pattern is not None:
        input_build_pattern = options.input_build_pattern
    else:
        input_build_pattern = default_input_build_pattern
        
    return (input_build_pattern, selected_input_build)
#------------------------------------------------------------------------------------------------------
def find_all(name_pat, path):
    result = []
    name_patc = re.compile(name_pat, re.IGNORECASE)
    for root, dirs, files in os.walk(path):
        for filename in files:
            if name_patc.match(filename):
                result.append(os.path.join(root, filename))
    return result

#------------------------------------------------------------------------------------------------------
def file_was_created_before(before_date, fileinfo):
    ret_val = False
    try:
        timestamp_str = fileinfo.date_str
        if timestamp_str < before_date:
            ret_val = True
        else:
            ret_val = False
    except Exception as e:
        ret_val = False # not found or error, return False
        
    return ret_val

#------------------------------------------------------------------------------------------------------
def file_was_created_after(after_date, fileinfo):
    ret_val = False
    try:
        timestamp_str = fileinfo.date_str
        if timestamp_str >  after_date:
            ret_val = True
        else:
            ret_val = False
    except Exception as e:
        ret_val = False # not found or error, return False
        
    return ret_val
#------------------------------------------------------------------------------------------------------
def file_was_loaded_before(solrcore, before_date, filename):
    ret_val = False
    try:
        result = opasSolrLoadSupport.get_file_dates_solr(solrcore, filename)
        if result[0]["timestamp"] < before_date:
            ret_val = True
        else:
            ret_val = False
    except Exception as e:
        ret_val = True # not found or error, return true
        
    return ret_val

#------------------------------------------------------------------------------------------------------
def file_was_loaded_after(solrcore, after_date, filename):
    ret_val = False
    try:
        result = opasSolrLoadSupport.get_file_dates_solr(solrcore, filename)
        if result[0]["timestamp"] > after_date:
            ret_val = True
        else:
            ret_val = False
    except Exception as e:
        ret_val = True # not found or error, return true
        
    return ret_val

#------------------------------------------------------------------------------------------------------
def file_is_same_or_newer_in_solr_by_artid(solrcore, art_id, timestamp_str, filename=None):
    """
    Now, since Solr may have EXP_ARCH1 and the load 'candidate' may be KBD3, the one in Solr
      can be the same or NEWER, and it's ok, no need to reprocess.
    """
    ret_val = False
    if filename is None:
        filename = art_id

    try:
        result = opasSolrLoadSupport.get_file_dates_solr(solrcore, art_id=art_id)
        if options.display_verbose:
            try:
                filetime = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ")
                filetime = filetime.strftime("%Y-%m-%d %H:%M:%S")
                solrtime = result[0]['file_last_modified']
                solrtime = datetime.strptime(solrtime, "%Y-%m-%dT%H:%M:%SZ")
                solrtime = solrtime.strftime("%Y-%m-%d %H:%M:%S")
                print (f"Skipped - No refresh needed File {filename}: {filetime} vs Solr: {solrtime}")
            except Exception as e:
                print (f"Skipped - No refresh needed File {filename}")

        if result[0]["file_last_modified"] >= timestamp_str:
            ret_val = True
        else:
            ret_val = False
    except KeyError as e:
        ret_val = False # not found, return false so it's loaded anyway.
    except Exception as e:
        logger.info(f"File check error: {e}")
        ret_val = False # error, return false so it's loaded anyway.
        
    return ret_val

#------------------------------------------------------------------------------------------------------
def file_is_same_as_in_solr(solrcore, filename, timestamp_str):
    ret_val = False
    try:
        result = opasSolrLoadSupport.get_file_dates_solr(solrcore, filename)
        if result[0]["file_last_modified"] == timestamp_str:
            ret_val = True
        else:
            ret_val = False
    except KeyError as e:
        ret_val = False # not found, return false so it's loaded anyway.
    except Exception as e:
        logger.info(f"File check error: {e}")
        ret_val = False # error, return false so it's loaded anyway.
        
    return ret_val

#------------------------------------------------------------------------------------------------------
def main():
    
    global options  # so the information can be used in support functions
    
    cumulative_file_time_start = time.time()
    randomizer_seed = None 

    # scriptSourcePath = os.path.dirname(os.path.realpath(__file__))

    processed_files_count = 0
    ocd =  opasCentralDBLib.opasCentralDB()
    fs = opasFileSupport.FlexFileSystem(key=localsecrets.S3_KEY, secret=localsecrets.S3_SECRET, root="pep-web-xml")

    # set toplevel logger to specified loglevel
    logger = logging.getLogger()
    logger.setLevel(options.logLevel)
    # get local logger
    logger = logging.getLogger(programNameShort)

    logger.info('Started at %s', datetime.today().strftime('%Y-%m-%d %H:%M:%S"'))
    # logging.basicConfig(filename=logFilename, level=options.logLevel)

    solrurl_docs = None
    solrurl_authors = None
    solrurl_glossary = None
    if options.rootFolder == localsecrets.XML_ORIGINALS_PATH or options.rootFolder == None:
        start_folder = pathlib.Path(localsecrets.XML_ORIGINALS_PATH)
    else:
        start_folder = pathlib.Path(options.rootFolder)   
    
    pre_action_verb = "Load"
    post_action_verb = "Loaded"
    if 1: # (options.biblio_update or options.fulltext_core_update or options.glossary_core_update) == True:
        try:
            solrurl_docs = localsecrets.SOLRURL + configLib.opasCoreConfig.SOLR_DOCS  # e.g., http://localhost:8983/solr/    + pepwebdocs'
            solrurl_authors = localsecrets.SOLRURL + configLib.opasCoreConfig.SOLR_AUTHORS
            solrurl_glossary = localsecrets.SOLRURL + configLib.opasCoreConfig.SOLR_GLOSSARY
            # print("Logfile: ", logFilename)
            print("Messaging verbose: ", options.display_verbose)
            print("Input data Root: ", start_folder)
            print("Input data Subfolder: ", options.subFolder)

            if options.loadprecompiled:
                input_build_pattern, selected_input_build = get_defaults(options, loaderConfig.default_precompiled_input_build_pattern, loaderConfig.default_precompiled_input_build)
                #if options.input_build_pattern is None:
                    #if options.input_build is None:
                        #input_build_pattern = loaderConfig.default_precompiled_input_build_pattern
                        #selected_input_build = loaderConfig.default_precompiled_input_build
                    #else:
                        #selected_input_build = input_build_pattern = options.input_build
                #else:
                    #input_build_pattern = options.input_build_pattern
                    #if options.input_build is None:
                        #selected_input_build = loaderConfig.default_precompiled_input_build
                    #else:
                        #if options.input_build == loaderConfig.default_input_build:
                            ## this is an error, no doubt, they are not Precompiled
                            #print (f"Error: cannot use {loaderConfig.default_input_build} as precompiled input build.  Changing to {loaderConfig.default_precompiled_input_build}")
                            #selected_input_build = loaderConfig.default_precompiled_input_build
                        #else:
                            #selected_input_build = options.input_build
                
                print(f"Precompiled XML of build {selected_input_build} will be loaded to the databases without further compiling/processing: ")
                pre_action_verb = "Load"
                post_action_verb = "Loaded"
                
            elif options.smartload:
                # compiled and loaded if input file is newer than output written file or if there's no output file
                input_build_pattern, selected_input_build = get_defaults(options, loaderConfig.default_input_build_pattern, loaderConfig.default_input_build)
                print(f"Input form of XML of build {input_build_pattern} will be compiled, saved, and loaded to the database unless already compiled version")
                pre_action_verb = "Smart compile, save and load"
                post_action_verb = "Smart compiled, saved and loaded"
                #selected_input_build = options.input_build
                
            elif options.compiletoload:
                # compiled and loaded
                input_build_pattern, selected_input_build = get_defaults(options, loaderConfig.default_input_build_pattern, loaderConfig.default_input_build)                    
                print(f"Input form of XML of build {input_build_pattern} will be compiled and loaded to the database")
                pre_action_verb = "Compile for Load only"
                post_action_verb = "Compiled to load"
                
            elif options.compiletosave:
                # written but not loaded
                input_build_pattern, selected_input_build = get_defaults(options, loaderConfig.default_input_build_pattern, loaderConfig.default_input_build)                    
                print(f"Input build {input_build_pattern} will be compiled to build {options.output_build} and saved to an XML file NOT loaded.")
                pre_action_verb = "Compile and Write"
                post_action_verb = "Compiled and Wrote"
                #selected_input_build = options.input_build
                
            elif options.compiletorebuild:
                # loaded and written
                input_build_pattern, selected_input_build = get_defaults(options, loaderConfig.default_input_build_pattern, loaderConfig.default_input_build)                    
                print(f"Input build {input_build_pattern} will be compiled to {options.output_build}, loaded, and written.")
                pre_action_verb = "Compile, Load and Write"
                post_action_verb = "Compiled, Loaded and Written"
                #selected_input_build = options.input_build
                
            print("Reset Core Data: ", options.resetCoreData)
            if options.forceRebuildAllFiles == True:
                msg = "Forced Rebuild - All files added, regardless of whether they are the same as in Solr."
                logger.info(msg)
                print (msg)
                
            print(80*"*")
            if not options.compiletosave:
                print(f"Database will be updated. Location: {localsecrets.DBHOST}")
                if not options.glossary_only: # options.fulltext_core_update:
                    print("Solr Full-Text Core will be updated: ", solrurl_docs)
                    print("Solr Authors Core will be updated: ", solrurl_authors)
                if 1: # options.glossary_core_update:
                    print("Solr Glossary Core will be updated: ", solrurl_glossary)
            
                print(80*"*")
                if options.include_paras:
                    print ("--includeparas option selected. Each paragraph will also be stored individually for *Docs* core. Increases core size markedly!")
                else:
                    try:
                        print (f"Paragraphs only stored for sources indicated in loaderConfig. Currently: [{', '.join(loaderConfig.src_codes_to_include_paras)}]")
                    except:
                        print ("Paragraphs only stored for sources indicated in loaderConfig.")
    
            if options.halfway:
                print ("--halfway option selected.  Including approximately one-half of the files that match.")
                
            if options.run_in_reverse:
                print ("--reverse option selected.  Running the files found in reverse order.")

            if options.file_key:
                print (f"--key supplied.  Including files matching the article id {options.file_key}.\n   ...Automatically implies force rebuild (--smartload) and/or reload (--load) of files.")

            print(80*"*")
            if not options.no_check and not options.compiletosave:
                cont = input ("The above databases will be updated.  Do you want to continue (y/n)?")
                if cont.lower() == "n":
                    print ("User requested exit.  No data changed.")
                    sys.exit(0)
                
        except Exception as e:
            msg = f"cores specification error ({e})."
            print((len(msg)*"-"))
            print (msg)
            print((len(msg)*"-"))
            sys.exit(0)

    # import data about the PEP codes for journals and books.
    #  Codes are like APA, PAH, ... and special codes like ZBK000 for a particular book
    sourceDB = opasProductLib.SourceInfoDB()
    solr_docs2 = None
    # The connection call is to solrpy (import was just solr)
    if localsecrets.SOLRUSER is not None and localsecrets.SOLRPW is not None:
        if 1: # options.fulltext_core_update:
            solr_docs2 = pysolr.Solr(solrurl_docs, auth=(localsecrets.SOLRUSER, localsecrets.SOLRPW))
    else: #  no user and password needed
        solr_docs2 = pysolr.Solr(solrurl_docs)

    # Reset core's data if requested (mainly for early development)
    if options.resetCoreData:
        if not options.glossary_only: # options.fulltext_core_update:
            if not options.no_check:
                cont = input ("The solr cores and the database article and artstat tables will be cleared.  Do you want to continue (y/n)?")
                if cont.lower() == "n":
                    print ("User requested exit.  No data changed.")
                    sys.exit(0)
            else:
                print ("Options --nocheck and --resetcore both specified.  Warning: The solr cores and the database article and artstat tables will be cleared.  Pausing 60 seconds to allow you to cancel (ctrl-c) the run.")
                time.sleep(60)
                print ("Second Warning: Continuing the run (and core and database reset) in 20 seconds...")
                time.sleep(20)               

            msg = "*** Deleting all data from the docs and author cores, the articles, artstat, and biblio database tables ***"
            logger.warning(msg)
            print (msg)
            ocd.delete_all_article_data()
            solr_docs2.delete(q='*:*')
            solr_docs2.commit()
            solr_authors2.delete(q="*:*")
            solr_authors2.commit()

        # reset glossary core when others are reset, or when --resetcore is selected with --glossaryonly   
        if 1: # options.glossary_core_update:
            msg = "*** Deleting all data from the Glossary core ***"
            logger.warning(msg)
            print (msg)
            solr_gloss2.delete(q="*:*")
            solr_gloss2.commit()
    else:
        pass   # XXX Later - check for missing files and delete them from the core, since we didn't empty the core above

    # Go through a set of XML files
    bib_total_reference_count = 0 # zero this here, it's checked at the end whether references are processed or not

    # ########################################################################
    # Get list of files to process    
    # ########################################################################
    new_files = 0
    total_files = 0
    
    if options.subFolder is not None:
        start_folder = start_folder / pathlib.Path(options.subFolder)

    # record time in case options.nofiles is true
    timeStart = time.time()

    if options.no_files == False: # process and/or load files (no_files just generates a whats_new list, no processing or loading)
        print (f"Locating files for processing at {start_folder} with build pattern {selected_input_build}. Started at ({time.ctime()}).")
        if options.file_key is not None:  
            # print (f"File Key Specified: {options.file_key}")
            # Changed from opasDataLoader (reading in bKBD3 files rather than EXP_ARCH1)
            pat = fr"({options.file_key})\({input_build_pattern}\)\.(xml|XML)$"
            print (f"Reading {pat} files")
            filenames = fs.get_matching_filelist(filespec_regex=pat, path=start_folder, max_items=1000)
            if len(filenames) is None:
                msg = f"File {pat} not found.  Exiting."
                logger.warning(msg)
                print (msg)
                exit(0)
            else:
                options.forceRebuildAllFiles = True
        elif options.file_only is not None: # File spec for a single file to process.
            fileinfo = FileInfo()
            filespec = options.file_only
            fileinfo.mapLocalFS(filespec)
            filenames = [fileinfo]
            print (f"Filenames: {filenames}")
        else:
            pat = fr"(.*?)\({selected_input_build}\)\.(xml|XML)$"
            filenames = []
        
        if filenames != []:
            total_files = len(filenames)
            new_files = len(filenames)
        else:
            # get a list of all the XML files that are new
            if options.forceRebuildAllFiles:
                # get a complete list of filenames for start_folder tree
                filenames = fs.get_matching_filelist(filespec_regex=pat, path=start_folder)
            else:
                filenames = fs.get_matching_filelist(filespec_regex=pat, path=start_folder, revised_after_date=options.created_after)
                
        print((80*"-"))
        files_found = len(filenames)
        if options.forceRebuildAllFiles:
            #maybe do this only during core resets?
            #print ("Clearing database tables...")
            #ocd.delete_all_article_data()
            print(f"Ready to {pre_action_verb} records from {files_found} files at path {start_folder}")
        else:
            print(f"Ready to {pre_action_verb} {files_found} files *if modified* at path: {start_folder}")
    
        timeStart = time.time()
        print (f"Processing started at ({time.ctime()}).")
    
        print((80*"-"))
        precommit_file_count = 0
        skipped_files = 0
        stop_after = 0
        cumulative_file_time_start = time.time()
        issue_updates = {}
        if files_found > 0:
            if options.halfway:
                stop_after = round(files_found / 2) + 5 # go a bit further
                
            if options.run_in_reverse:
                filenames.reverse()
            
            # ----------------------------------------------------------------------
            # Now walk through all the filenames selected
            # ----------------------------------------------------------------------
            print (f"{pre_action_verb} started ({time.ctime()}).  Examining files.")
            
            for n in filenames:
                fileTimeStart = time.time()
                file_updated = False
                smart_file_rebuild = False
                base = n.basename
                artID = os.path.splitext(base)[0]
                m = re.match(r"([^ ]*).*\(.*\)", artID)
                artID = m.group(1)
                artID = artID.upper()
                
                if not options.forceRebuildAllFiles:  # always force processed for single file                  
                    if not options.display_verbose and processed_files_count % 100 == 0 and processed_files_count != 0:
                        print (f"Processed Files ...loaded {processed_files_count} out of {files_found} possible.")
    
                    if not options.display_verbose and skipped_files % 100 == 0 and skipped_files != 0:
                        print (f"Skipped {skipped_files} so far...loaded {processed_files_count} out of {files_found} possible." )
                    
                    if file_is_same_or_newer_in_solr_by_artid(solr_docs2, art_id=artID, timestamp_str=n.timestamp_str, filename=n.basename):
                        skipped_files += 1
                        # moved to file_is_same_or_newer_in_solr_by_artid
                        #if options.display_verbose:
                            #print (f"Skipped - No refresh needed for {n.basename}")
                        continue
                    else:
                        file_updated = True
                
                # get mod date/time, filesize, etc. for mysql database insert/update
                processed_files_count += 1
                if stop_after > 0:
                    if processed_files_count > stop_after:
                        print (f"Halfway mark reached on file list ({stop_after})...file processing stopped per halfway option")
                        break

                if options.smartload:
                    if options.forceRebuildAllFiles:
                        smart_file_rebuild = True
                    else:
                        # see if the output file exists and is older than the input file
                        outputfname = str(n.filespec)
                        outputfname = outputfname.replace(selected_input_build, options.output_build)
                        fileinfoinp = FileInfo()
                        try:
                            fileinfoinp.mapLocalFS(outputfname)
                            if fileinfoinp.date_modified <  n.date_modified:
                                # need to rebuild
                                smart_file_rebuild = True
                            else:
                                smart_file_rebuild = False
                                n = fileinfoinp
                        except Exception as e:
                            #print (e)
                            smart_file_rebuild = True
                        else:
                            smart_file_rebuild = False
                            if options.display_verbose:
                                print (f"SmartLoad: Loading only. No need to rebuild: {outputfname}.")
                
                # Read file    
                fileXMLContents = fs.get_file_contents(n.filespec)
                
                # get file basename without build (which is in paren)
                #base = n.basename
                #artID = os.path.splitext(base)[0]
                # watch out for comments in file name, like:
                #   JICAP.018.0307A updated but no page breaks (bEXP_ARCH1).XML
                #   so skip data after a space
                msg = "Processing file #%s of %s: %s (%s bytes). Art-ID:%s" % (processed_files_count, files_found, n.basename, n.filesize, artID)
                logger.info(msg)
                if options.display_verbose:
                    print (80 * "-")
                    print (msg)
        
                # import into lxml
                parser = lxml.etree.XMLParser(encoding='utf-8', recover=True, resolve_entities=True, load_dtd=True)
                parsed_xml = etree.fromstring(opasxmllib.remove_encoding_string(fileXMLContents), parser)
                #treeroot = pepxml.getroottree()
                #root = pepxml.getroottree()
        
                # save common document (article) field values into artInfo instance for both databases
                artInfo = opasSolrLoadSupport.ArticleInfo(sourceDB.sourceData, parsed_xml, artID, logger)
                artInfo.filedatetime = n.timestamp_str
                artInfo.filename = base
                artInfo.file_size = n.filesize
                artInfo.file_updated = file_updated
                artInfo.file_create_time = n.create_time
                
                # not a new journal, see if it's a new article.
                if opasSolrLoadSupport.add_to_tracker_table(ocd, artInfo.art_id): # if true, added successfully, so new!
                    # don't log to issue updates for journals that are new sources added during the annual update
                    if artInfo.src_code not in loaderConfig.DATA_UPDATE_PREPUBLICATION_CODES_TO_IGNORE:
                        art = f"<article id='{artInfo.art_id}'>{artInfo.art_citeas_xml}</article>"
                        try:
                            issue_updates[artInfo.issue_id_str].append(art)
                        except Exception as e:
                            issue_updates[artInfo.issue_id_str] = [art]
    
                try:
                    artInfo.file_classification = re.search("(?P<class>current|archive|future|free|special|offsite)", str(n.filespec), re.IGNORECASE).group("class")
                    # set it to lowercase for ease of matching later
                    if artInfo.file_classification is not None:
                        artInfo.file_classification = artInfo.file_classification.lower()
                except Exception as e:
                    logger.warning("Could not determine file classification for %s (%s)" % (n.filespec, e))
                
                if options.compiletosave or options.compiletorebuild or options.compiletoload or smart_file_rebuild:
                    # make changes to the XML
                    parsed_xml, ret_status = opasXMLProcessor.xml_update(parsed_xml, artInfo, ocd, pretty_print=options.pretty_printed, verbose=options.display_verbose)
                    # impx_count = int(pepxml.xpath('count(//impx[@type="TERM2"])'))
                    # print (impx_count, fileXMLContents[500:2500])
                    if not options.compiletoload: # save it
                        # write output file
                        fname = str(n.filespec)
                        fname = re.sub("\(b.*\)", options.output_build, fname)
                        
                        msg = f"\t...Exporting! Writing compiled file to {fname}"
                        if options.display_verbose:
                            print (msg)

                        root = parsed_xml.getroottree()
                        root.write(fname, encoding="utf-8", method="xml", pretty_print=True, xml_declaration=True, doctype=options.output_doctype)
                    
                        # xml_text version, not reconverted to tree
                        #file_text = lxml.etree.tostring(parsed_xml, pretty_print=options.pretty_printed, encoding="utf8").decode("utf-8")
                        #fname = fname.replace(options.output_build, "(bXML_TEXT)")
                        #with open(fname, 'w', encoding="utf8") as fo:
                            #fo.write( f'<?xml version="1.0" encoding="UTF-8"?>\n')
                            #fo.write(file_text)

                    if options.compiletosave:
                        continue # next document -- no need to do anything else for this doc

                # walk through bib section and add to refs core database
                precommit_file_count += 1
                if precommit_file_count > configLib.opasCoreConfig.COMMITLIMIT:
                    print(f"Committing info for {configLib.opasCoreConfig.COMMITLIMIT} documents/articles")
    
                # input to the glossary
                if 1: # options.glossary_core_update:
                    # load the glossary core if this is a glossary item
                    glossary_file_pattern=r"ZBK.069(.*)\(bEXP_ARCH1\)\.(xml|XML)$"
                    if re.match(glossary_file_pattern, n.basename):
                        opasSolrLoadSupport.process_article_for_glossary_core(parsed_xml, artInfo, solr_gloss2, fileXMLContents, verbose=options.display_verbose)
                
                # input to the full-text and authors cores
                if not options.glossary_only: # options.fulltext_core_update:
                    # load the database
                    opasSolrLoadSupport.add_article_to_api_articles_table(ocd, artInfo, verbose=options.display_verbose)
                    opasSolrLoadSupport.add_to_artstat_table(ocd, artInfo, verbose=options.display_verbose)

                    # -----
                    # 2022-04-22 New Section Name Workaround - This works but it means at least for new data, you can't run the load backwards as we currently do
                    #  on a full build.  Should be put into the client instead, really, during table gen.
                    # -----
                    # Uses new views: vw_article_firstsectnames which is based on the new view vw_article_sectnames
                    #  if an article id is found in that view, it's the first in the section, otherwise it isn't
                    # check database to see if this is the first in the section
                    if not opasSolrLoadSupport.check_if_start_of_section(ocd, artInfo.art_id):
                        # print (f"\t\t...NewSec Workaround: Clearing newsecnm for {artInfo.art_id}")
                        artInfo.start_sectname = None # clear it so it's not written to solr, this is not the first article
                    else:
                        if options.display_verbose:
                            print (f"\t\t...NewSec {artInfo.start_sectname} found in {artInfo.art_id}")
                    # -----

                    # load the docs (pepwebdocs) core
                    opasSolrLoadSupport.process_article_for_doc_core(parsed_xml, artInfo, solr_docs2, fileXMLContents, include_paras=options.include_paras, verbose=options.display_verbose)
                    # load the authors (pepwebauthors) core.
                    opasSolrLoadSupport.process_info_for_author_core(parsed_xml, artInfo, solr_authors2, verbose=options.display_verbose)
                    # load the database (Moved to above new section name workaround)
                    #opasSolrLoadSupport.add_article_to_api_articles_table(ocd, artInfo, verbose=options.display_verbose)
                    #opasSolrLoadSupport.add_to_artstat_table(ocd, artInfo, verbose=options.display_verbose)
                    
                    if precommit_file_count > configLib.opasCoreConfig.COMMITLIMIT:
                        precommit_file_count = 0
                        solr_docs2.commit()
                        solr_authors2.commit()
                    
                # Add to the references table
                if 1: # options.biblio_update:
                    if artInfo.ref_count > 0:
                        bibReferences = parsed_xml.xpath("/pepkbd3//be")  # this is the second time we do this (also in artinfo, but not sure or which is better per space vs time considerations)
                        if options.display_verbose:
                            print(("\t...Processing %s references for the references database." % (artInfo.ref_count)))
    
                        #processedFilesCount += 1
                        bib_total_reference_count = 0
                        ocd.open_connection(caller_name="processBibliographies")
                        for ref in bibReferences:
                            bib_total_reference_count += 1
                            bib_entry = opasSolrLoadSupport.BiblioEntry(artInfo, ref)
                            opasSolrLoadSupport.add_reference_to_biblioxml_table(ocd, artInfo, bib_entry)
    
                        try:
                            ocd.db.commit()
                        except mysql.connector.Error as e:
                            print("SQL Database -- Biblio Commit failed!", e)
                            
                        ocd.close_connection(caller_name="processBibliographies")
    
                # close the file, and do the next
                if options.display_verbose:
                    print(("\t...Time: %s seconds." % (time.time() - fileTimeStart)))
        
            print (f"{pre_action_verb} process complete ({time.ctime()} ). Time: {time.time() - fileTimeStart} seconds.")
            if processed_files_count > 0 and not options.compiletosave:
                try:
                    print ("Performing final commit.")
                    if not options.glossary_only: # options.fulltext_core_update:
                        solr_docs2.commit()
                        solr_authors2.commit()
                        # fileTracker.commit()
                    if 1: # options.glossary_core_update:
                        solr_gloss2.commit()
                except Exception as e:
                    print(("Exception: ", e))
                else:
                    # Use date time as seed, hoping multiple instances don't get here at the same time
                    # but only if caller did not specify
                    if randomizer_seed is None:
                        randomizer_seed = int(datetime.utcnow().timestamp())
    
    opasSolrLoadSupport.garbage_collect_stat(ocd)
    if options.daysback is not None: #  get all updated records
        print (f"Listing updates for {options.daysback} days.")
        issue_updates = {}
        try:
            days_back = int(options.daysback)
        except:
            logger.error("Incorrect specification of days back. Must be integer.")
        else:
            article_list = ocd.get_articles_newer_than(days_back=days_back)
            for art_id in article_list:
                artInfoSolr = opasAPISupportLib.documents_get_abstracts(art_id)
                try:
                    art_citeas_xml = artInfoSolr.documents.responseSet[0].documentRefXML
                    src_code = artInfoSolr.documents.responseSet[0].PEPCode
                    art_year = artInfoSolr.documents.responseSet[0].year
                    art_vol_str = artInfoSolr.documents.responseSet[0].vol
                    art_issue = artInfoSolr.documents.responseSet[0].issue
                    issue_id_str = f"<issue_id><src>{src_code}</src><yr>{art_year}</yr><vol>{art_vol_str}</vol><iss>{art_issue}</iss></issue_id>"
                except:
                    logger.error(f"Error: can't find article info for: {art_id} ")
                else:   
                    if src_code not in loaderConfig.DATA_UPDATE_PREPUBLICATION_CODES_TO_IGNORE:
                        art = f"<article id='{art_id}'>{art_citeas_xml}</article>"
                        try:
                            issue_updates[issue_id_str].append(art)
                        except Exception as e:
                            issue_updates[issue_id_str] = [art]
    if issue_updates != {}:
        random.seed(randomizer_seed)
        try:
            if options.whatsnewfile is None:
                try:
                    fname = f"{localsecrets.DATA_UPDATE_LOG_DIR}/updated_issues_{dtime.datetime.now().strftime('%Y%m%d_%H%M%S')}({random.randint(1000,9999)}).xml"
                except Exception as e:
                    fname = f"updated_issues_{dtime.datetime.now().strftime('%Y%m%d_%H%M%S')}({random.randint(1000,9999)}).xml"
            else:
                fname = options.whatsnewfile
            msg = f"Writing Issue updates.  Writing to file {fname}"
            print (msg)
            logging.info(msg)
            with open(fname, 'w', encoding="utf8") as fo:
                fo.write( f'<?xml version="1.0" encoding="UTF-8"?>\n')
                fo.write('<issue_updates>\n')
                count_records = 0
                for k, a in issue_updates.items():
                    fo.write(f"\n\t<issue>\n\t\t{str(k)}\n\t\t<articles>\n")
                    count_records += 1
                    for ref in a:
                        try:
                            fo.write(f"\t\t\t{ref}\n")
                        except Exception as e:
                            logging.error(f"Issue Update Article Write Error: ({e})")
                    fo.write("\t\t</articles>\n\t</issue>")
                fo.write('\n</issue_updates>')
            if count_records > 0:
                print (f"{count_records} issue updates written to whatsnew log file.")

        except Exception as e:
            logging.error(f"Issue Update File Write Error: ({e})")
    else: # if issue_updates != {}
        if options.daysback is not None:
            msg = f"Note: There was nothing in the whats new request to output for days back == {options.daysback}."
            logging.warning(msg)
        else:
            msg = f"Note: There was nothing new in the batch output whatsnew."
            logging.warning(msg)
    # ---------------------------------------------------------
    # Closing time
    # ---------------------------------------------------------
    timeEnd = time.time()
    #currentfile_info.close()

    if not options.no_files: # no_files=false
        # for logging
        if 1: # (options.biblio_update or options.fulltext_core_update) == True:
            elapsed_seconds = timeEnd-cumulative_file_time_start # actual processing time going through files
            elapsed_minutes = elapsed_seconds / 60
            if bib_total_reference_count > 0:
                msg = f"Finished! {post_action_verb} {processed_files_count} documents and {bib_total_reference_count} references. Total file inspection/load time: {elapsed_seconds:.2f} secs ({elapsed_minutes:.2f} minutes.) "
                logger.info(msg)
                print (msg)
            else:
                msg = f"Finished! {post_action_verb} {processed_files_count} documents {options.output_build}. Total file load time: {elapsed_seconds:.2f} secs ({elapsed_minutes:.2f} minutes.)"
                logger.info(msg) 
                print (msg)
            if processed_files_count > 0:
                msg = f"...Files per Min: {processed_files_count/elapsed_minutes:.4f}"
                logger.info(msg)
                print (msg)
                msg = f"...Files evaluated per Min (includes skipped files): {len(filenames)/elapsed_minutes:.4f}"
                logger.info(msg)
                print (msg)
    
        elapsed_seconds = timeEnd-timeStart # actual processing time going through files
        elapsed_minutes = elapsed_seconds / 60
        msg = f"Note: File load time is not total elapsed time. Total elapsed time is: {elapsed_seconds:.2f} secs ({elapsed_minutes:.2f} minutes.)"
        logger.info(msg)
        print (msg)
        if processed_files_count > 0:
            msg = f"Files per elapsed min: {processed_files_count/elapsed_minutes:.4f}"
            logger.info(msg)
            print (msg)
    else:  # no_files=True, just generates a whats_new list, no processing or loading
        print ("Processing finished.")
        elapsed_seconds = timeEnd-timeStart # actual processing time going through files
        elapsed_minutes = elapsed_seconds / 60
        msg = f"Elapsed min: {elapsed_minutes:.4f}"
        logger.info(msg)
        print (msg)

# -------------------------------------------------------------------------------------------------------
# run it!

if __name__ == "__main__":
    global options  # so the information can be used in support functions
    options = None
    parser = OptionParser(usage="%prog [options] - PEP Solr Data Loader", version=f"%prog ver. {__version__}")
    parser.add_option("-a", "--allfiles", action="store_true", dest="forceRebuildAllFiles", default=False,
                      help="Option to force all files to be loaded to the specified cores.")
    # redundant add option to use so compatible options to the PEPXML code for manual use
    parser.add_option("--rebuild", "--reload", action="store_true", dest="forceRebuildAllFiles", default=False,
                      help="Option to force one or more included files to be reloaded to the specified cores whether changed or not.")
    parser.add_option("--after", dest="created_after", default=None,
                      help="Load files created or modifed after this datetime (use YYYY-MM-DD format). (May not work on S3)")
    parser.add_option("-d", "--dataroot", dest="rootFolder", default=localsecrets.XML_ORIGINALS_PATH,
                      help="Bucket (Required S3) or Root folder path where input data is located")
    parser.add_option("--key", dest="file_key", default=None,
                      help="Key for a single file to load, e.g., AIM.076.0269A.  Use in conjunction with --sub for faster processing of single files on AWS")
    parser.add_option("-l", "--loglevel", dest="logLevel", default=logging.ERROR,
                      help="Level at which events should be logged (DEBUG, INFO, WARNING, ERROR")
    #parser.add_option("--logfile", dest="logfile", default=logFilename,
                      #help="Logfile name with full path where events should be logged")
    parser.add_option("--nocheck", action="store_true", dest="no_check", default=False,
                      help="Don't prompt whether to proceed.")
    parser.add_option("--only", dest="file_only", default=None,
                      help="File spec for a single file to process.")
    parser.add_option("--includeparas", action="store_true", dest="include_paras", default=False,
                      help="Don't separately store paragraphs except for sources using concordance (GW/SE).")
    parser.add_option("--halfway", action="store_true", dest="halfway", default=False,
                      help="Only process halfway through (e.g., when running forward and reverse.")
    parser.add_option("--glossaryonly", action="store_true", dest="glossary_only", default=False,
                      help="Only process the glossary (quicker).")
    parser.add_option("--pw", dest="httpPassword", default=None,
                      help="Password for the server")
    parser.add_option("-r", "--reverse", dest="run_in_reverse", action="store_true", default=False,
                      help="Whether to run the selected files in reverse order")
    parser.add_option("--resetcore",
                      action="store_true", dest="resetCoreData", default=False,
                      help="clear (delete) any data in the selected cores (author core is reset with the fulltext core).")
    parser.add_option("--seed",
                      dest="randomizer_seed", default=None,
                      help="Seed so data update files don't collide if they start writing at exactly the same time.")
    parser.add_option("--sub", dest="subFolder", default=None,
                      help="Sub folder of root folder specified via -d to process")
    parser.add_option("--test", dest="testmode", action="store_true", default=False,
                      help="Run Doctests")
    parser.add_option("--userid", dest="httpUserID", default=None,
                      help="UserID for the server")
    parser.add_option("--verbose", action="store_true", dest="display_verbose", default=False,
                      help="Display status and operational timing info as load progresses.")
    parser.add_option("--nofiles", action="store_true", dest="no_files", default=False,
                      help="Don't load any files (use with whatsnewdays to only generate a whats new list).")
    parser.add_option("--whatsnewdays", dest="daysback", default=None,
                      help="Generate a log of files added in the last n days (1==today), rather than for files added during this run.")
    parser.add_option("--whatsnewfile", dest="whatsnewfile", default=None,
                      help="File name to force the file and path rather than a generated name for the log of files added in the last n days.")
    # New OpasLoader2 Options
    parser.add_option("--inputbuildpattern", dest="input_build_pattern", default=None,
                      help="Pattern of the build specifier to load (input), e.g., (bEXP_ARCH1|bSeriesTOC), or (bKBD3|bSeriesTOC)")
    
    parser.add_option("--inputbuild", dest="input_build", default=None,
                      help=f"Build specifier to load (input), e.g., (bKBD3) or just bKBD3")
    
    parser.add_option("--outputbuild", dest="output_build", default=loaderConfig.default_output_build,
                      help=f"Specific output build specification, default='{loaderConfig.default_output_build}'. e.g., (bEXP_ARCH1) or just bEXP_ARCH1.")
    
    # --load option still the default.  Need to keep for backwards compatibility, at least for now (7/2022)
    parser.add_option("--load", "--loadxml", action="store_true", dest="loadprecompiled", default=True,
                      help="Load already compiled XML, e.g. (bEXP_ARCH1) into database.")

    parser.add_option("--smartload", "--smartbuild", action="store_true", dest="smartload", default=False,
                      help="Load already processed XML (e.g., bEXP_ARCH1), or if needed, compile unprocessed XML (e.g., bKBD3) into processed format, and load into database.")

    parser.add_option("--compiletoload", "--compileload", action="store_true", dest="compiletoload", default=False,
                      help="Compile input XML (e.g., (bKBD3) to a processed build of XML (don't save) AND load into database.  Much slower, since it must always process, not recommended.")
    
    parser.add_option("--compiletosave", "--compilesave", action="store_true", dest="compiletosave", default=False,
                      help="Compile input XML (e.g., (bKBD3) to processed XML. Just save compiled XML to the output build (e.g., (bEXP_ARCH1), for later loading")

    parser.add_option("--compiletorebuild", "--compilerebuild", action="store_true", dest="compiletorebuild", default=False,
                      help="Compile input XML (e.g., (bKBD3) to a processed build of XML, Save, AND load into database.")

    parser.add_option("--prettyprint", action="store_true", dest="pretty_printed", default=True,
                      help="Pretty format the compiled XML.")

    parser.add_option("--nohelp", action="store_true", dest="no_help", default=False,
                      help="Turn off front-matter help")

    parser.add_option("--doctype", dest="output_doctype", default=loaderConfig.default_doctype,
                      help=f"""For output files, default={loaderConfig.default_doctype}.""")

    #parser.add_option("-w", "--writexml", "--writeprocessed", action="store_true", dest="write_processed", default=False,
                      #help="Write the processed data to files, using the output build (e.g., (bEXP_ARCH1).")
    #parser.add_option("--noload", action="store_true", dest="no_load", default=False,
                      #help="for use with option writeprocessed, don't load Solr...just process.")

    (options, args) = parser.parse_args()
    
    if options.smartload:
        options.loadprecompiled = False # override default
    
    if not (options.loadprecompiled or options.compiletoload or options.compiletosave or options.compiletorebuild):
        options.smartload = True
    
    if not options.no_help:
        print (help_text)

    if len(options.output_build) < 2:
        logger.error("Bad output buildname. Using default.")
        options.output_build = '(bEXP_ARCH1)'
        
    if options.output_build is not None and (options.output_build[0] != "(" or options.output_build[-1] != ")"):
        print ("Warning: output build should have parenthesized format like (bEXP_ARCH1). Adding () as needed.")
        if options.output_build[0] != "(":
            options.output_build = f"({options.output_build}"
        if options.output_build[-1] != ")":
            options.output_build = f"{options.output_build})"
    
    if options.input_build is not None and (options.input_build[0] != "(" or options.input_build[-1] != ")"):
        print ("Warning: input build should have parenthesized format like (bKBD3). Adding () as needed.")
        if options.input_build[0] != "(":
            options.input_build = f"({options.input_build}"
        if options.input_build[-1] != ")":
            options.input_build = f"{options.input_build})"

    if options.glossary_only and options.file_key is None:
        options.file_key = "ZBK.069"

    if options.testmode:
        import doctest
        doctest.testmod()
        print ("Fini. opasDataLoader Tests complete.")
        sys.exit()


    main()
