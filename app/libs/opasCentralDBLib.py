#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
opasCentralDBLib

This library is supports the main functionality of the OPAS Central Database

The database has use and usage information.

OPASCENTRAL TABLES (and Views) CURRENTLY USED:
   vw_stat_most_viewed (depends on vw_stat_docviews_crosstab,
                                   table articles)

   vw_stat_docviews_crosstab (depends on api_docviews,
                                         vw_stat_docviews_lastmonth,
                                         vw_stat_docviews_lastsixmonths,
                                         vw_stat_docviews_lastcalyear,
                                         vw_stat_docviews_last12months
                                         )

   vw_stat_cited_crosstab (depends on fullbiblioxml - table copied from PEP XML Processing db pepa1db
                           vw_stat_cited_in_last_5_years,
                           vw_stat_cited_in_last_10_years,
                           vw_stat_cited_in_last_20_years,
                           vw_stat_cited_in_all_years
                           )                                        
    
    vw_api_productbase_instance_counts (this is the ISSN table from pepa1vdb used during processing)
    
    Used in generators:
    
      vw_stat_cited_crosstab_with_details (depeds on vw_stat_cited_crosstab + articles)
      vw_stat_most_viewed

"""
#2019.0708.1 - Python 3.7 compatible. 
#2019.1110.1 - Updates for database view/table naming cleanup
#2020.0426.1 - Updates to ensure doc tests working, a couple of parameters changed names
#2020.0530.1 - Fixed doc tests for termindex, they were looking at number of terms rather than term counts
#2021.0321.1 - Set up to allow connection to multiple databases to allow copying from stage to production dbs

__author__      = "Neil R. Shapiro"
__copyright__   = "Copyright 2020-2021, Psychoanalytic Electronic Publishing"
__license__     = "Apache 2.0"
__version__     = "2021.0602.1"
__status__      = "Development"

import sys
import re
# import fnmatch

# import os.path
from contextlib import closing

sys.path.append('../libs')
sys.path.append('../config')

from fastapi import Depends

import opasConfig
from opasConfig import normalize_val # use short form everywhere

import localsecrets
# from localsecrets import DBHOST, DBUSER, DBPW, DBNAME

import logging
logger = logging.getLogger(__name__)
import starlette.status as httpCodes

import datetime as dtime
from datetime import datetime # , timedelta
import time

# import secrets
# from pydantic import BaseModel
from passlib.context import CryptContext
# from pydantic import ValidationError

import mysql.connector
# import pymysql
# import jwt
import json

#import opasAuthBasic
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# import requests
import xml.etree.ElementTree as ET

import models

# All opasCentral Database Models here
import models

DEFAULTSESSIONLENGTH = 1800 # seconds (timeout)
API_STATUS_SUCCESS = "Success"
API_STATUS_ERROR = "Error"
API_ENDPOINT_METHOD_GET = "get"
API_ENDPOINT_METHOD_PUT = "put"
API_ENDPOINT_METHOD_POST = "post"
API_ENDPOINT_METHOD_DELETE = "delete"

# ##########################################################################
# API SYMBOLIC ENDPOINTS MUST MATCH API_ENDPOINTS TABLE IN DB!!!!
# 
# Commented values are not currently recorded in the session_endpoint table
# ##########################################################################
# API_LOGIN = 1	                             # /Login/
# API_LOGIN_STATUS = 2	                     # /License/Status/Login/
# API_LOGOUT = 3      	                     # /Logout/                
# API_ALERTS = 6                             # No endpoint currently
API_ADMIN_REPORTS = 7                        # /Admin/Reports
# API_OPENAPISPEC = 8                        # /Api/Openapispec
# API_LIVEDOC = 9                            # /Api/Livedoc
# API_METADATA_BANNERS = 10	                 # /Metadata/Banners/
# API_METADATA_BANNERS_FOR_PEPCODE = 11	     # /Metadata/Banners/{pepcode}/
# API_METADATA_SOURCEINFO = 12	             # /Metadata/{sourceType}/
# API_METADATA_SOURCEINFO_FOR_PEPCODE = 13	 # /Metadata/{sourceType}/{pepCode}/
# API_METADATA_VOLUME_INDEX = 14	         # /Metadata/Volumes/{pepCode}/
# API_METADATA_CONTENTS = 15	             # /Metadata/Contents/{pepCode}/
# API_METADATA_CONTENTS_FOR_VOL = 16	     # /Metadata/Contents/{pepCode}/{pepVol}/
# API_METADATA_BOOKS = 17	                 # /Metadata/Contents/Books/{bookBaseDocumentID}/
# API_METADATA_ARTICLEID = 18                # /Metadata/ArticleID/
# API_AUTHORS_INDEX = 20	                 # /Authors/Index/{authNamePartial}/
# API_AUTHORS_PUBLICATIONS = 21	             # /Authors/Publications/{authNamePartial}/
API_DOCUMENTS_ABSTRACTS = 30	             # /Documents/Abstracts/{documentID}/
API_DOCUMENTS = 31                       	 # /Documents/{documentID}/
API_DOCUMENTS_PDF = 32	                     # /Documents/Downloads/PDF/{documentID}/
API_DOCUMENTS_PDFORIG = 33	                 # /Documents/Downloads/PDFORIG/{documentID}/
# = 34 is open!
API_DOCUMENTS_EPUB = 35	                     # /Documents/Downloads/PDF/{documentID}/
API_DOCUMENTS_HTML = 36	                     # /Documents/Downloads/HTML/{documentID}/
API_DOCUMENTS_IMAGE = 37	                 # /Documents/Image/{imageID}/?download=1
API_DOCUMENTS_CONCORDANCE = 38	             # /Documents/Paragraph/Concordance/
API_DOCUMENTS_GLOSSARY_TERM = 39             # /Documents/Glossary/Term 
# API_DATABASE_SEARCHANALYSIS_FOR_TERMS = 40 # /Database/SearchAnalysis/{searchTerms}/
API_DATABASE_SEARCH = 41	                 # /Database/Search/
# API_DATABASE_WHATSNEW = 42	             # /Database/WhatsNew/
API_DATABASE_MOSTCITED = 43	                 # /Database/MostCited/
API_DATABASE_MOSTVIEWED = 44	             # /Database/MostViewed/ 
# API_DATABASE_SEARCHANALYSIS = 45	         # /Database/SearchAnalysis/
API_DATABASE_ADVANCEDSEARCH = 46	         # /Database/AdvancedSearch/
# API_DATABASE_TERMCOUNTS = 47               # /Database/TermCounts/
API_DATABASE_GLOSSARY_SEARCH = 48	         # /Database/Search/
API_DATABASE_EXTENDEDSEARCH = 49             # /Database/ExtendedSearch/
# API_DATABASE_SEARCHTERMLIST = 50           # No endpoint currently
# API_DATABASE_CLIENT_CONFIGURATION = 51     # /Client/Configuration
API_DATABASE_OPENURL = 52	                 # /Database/OpenURL/
API_DATABASE_WHOCITEDTHIS = 53               # /Database/WhoCitedThis/
API_DATABASE_MORELIKETHIS = 54               # /Database/MoreLikeThis/
API_DATABASE_RELATEDTOTHIS = 55              # /Database/RelatedDocuments/

def date_to_db_date(std_date):
    ret_val = None
    if type(std_date) == type("str"):
        try:
            ret_val = datetime.strftime(datetime.strptime(std_date, opasConfig.TIME_FORMAT_STR), opasConfig.TIME_FORMAT_STR_DB)
        except Exception as e:
            logger.error(e)
    else:
        try: # see if it's a regular date object
            ret_val = datetime.strftime(std_date, opasConfig.TIME_FORMAT_STR_DB)
        except Exception as e:
            logger.error(e)
            
    return ret_val
    

#def verifyAccessToken(session_id, username, access_token):
    #return pwd_context.verify(session_id+username, access_token)
    #removed 2021-12-07
    
def verify_password(plain_password, hashed_password):
    """
    >>> verify_password("secret", get_password_hash("secret"))
    True

    >>> verify_password("temporaryLover", '$2b$12$dy27eHxQoeekTMQIlofzvekWPr1rgrGp1fmXbWcQwCQynFkqvDH62')
    True
    
    >>> verify_password("temporaryLover", '$2b$12$0VH2W6CPxJdARmEcVQ7S9.FWk.xC41KdwN1e5XS2wuhbPYNRCFrmy')
    True
    
    >>> verify_password("pakistan", '$2b$12$VRLAkonDGCEuavaSotvbhOf.bVV0GDNysja.cHBFrrYHZw3e2vV7C')
    True

    >>> verify_password("pakistan", '$2b$12$z7F1BD8NhgcuBq090omf1.PfmP6obAaFN0QGyU1n/Gqv2oUvU9CGy')
    False

    """
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    """
    Returns the hashed password that's stored
    >>> get_password_hash("doogie")
    '...'
    """
    return pwd_context.hash(password)

class ErrorMessageDB(object):
    def __init__(self):
        self.message_data = {}
        ocd = opasCentralDB()
        recs = ocd.get_user_errormsg_data()
        for n in recs:
            try:
                self.message_data[n["pepsrccode"]] = n
            except KeyError:
                logger.error("Missing Source Code Value in %s" % n)

    def lookupSourceCode(self, sourceCode):
        """
        Returns the dictionary entry for the source code or None
          if it doesn't exist.
        """
        dbEntry = self.sourceData.get(sourceCode, None)
        retVal = dbEntry
        return retVal
    

class opasCentralDB(object):
    """
    This object should be used and then discarded on an endpoint by endpoint basis in any
      multiuser mode.
      
    Therefore, keeping session info in the object is ok,
    
    >> random_session_id = secrets.token_urlsafe(16)
    >>> import opasDocPermissions
    >>> UNIT_TEST_CLIENT_ID = "4"
    >>> session_info = opasDocPermissions.get_authserver_session_info(session_id=None, client_id=UNIT_TEST_CLIENT_ID)
    >>> session_id = session_info.session_id
    >>> session_id
    '...'
    >>> ocd.end_session(session_info.session_id)
    True

    # don't delete, do it manually
    > ocd.delete_session(session_id=random_session_id)
    True
    """
    connection_count = 0
    
    def __init__(self, session_id=None,
                 host=localsecrets.DBHOST,
                 port=localsecrets.DBPORT,
                 user=localsecrets.DBUSER,
                 password=localsecrets.DBPW,
                 database=localsecrets.DBNAME):

        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.connected = False
        self.db = None
        self.library_version = self.get_mysql_version()
        self.session_id = session_id # deprecate?

    def __del__(self):
        pass
        
    def open_connection(self, caller_name=""):
        """
        Opens a connection - Try Always!
        
        If already open, no changes.
        >>> ocd = opasCentralDB()
        >>> ocd.open_connection("my name")
        True
        >>> ocd.close_connection("my name")
        """
        try:
            opasCentralDB.connection_count += 1
            self.db = mysql.connector.connect(user=self.user, password=self.password, database=self.database, host=self.host)
            self.connected = True
            # logger.debug(f"Opened connection #{opasCentralDB.connection_count}")

        except Exception as e:
            self.connected = False
            opasCentralDB.connection_count -= 1
            logger.error(f"Database connection could not be opened ({caller_name}) ({e}). Opening connection number: {opasCentralDB.connection_count}")
            self.db = None
        
        return self.connected

    def close_connection(self, caller_name=""):
        try:
            opasCentralDB.connection_count -= 1
            self.db.close()
            self.db = None
            # logger.debug(f"Database closed by ({caller_name})")
                
        except Exception as e:
            opasCentralDB.connection_count = 0
            logger.info(f"caller: {caller_name} the db is not open ({e}).")

        self.connected = False
        return self.connected

    def end_session(self, session_id, session_end=datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')):
        """
        End the session
        
        Tested in main instance docstring
        """
        fname = "end_session"
        ret_val = False
        session_info = self.get_session_from_db(session_id)
        if session_info is not None:
            self.open_connection(caller_name=fname) # make sure connection is open
            if self.db is not None:
                if session_id is not None:
                    try:
                        with closing(self.db.cursor()) as cursor:
                            sql = """UPDATE api_sessions
                                     SET session_end = %s
                                     WHERE session_id = %s
                                  """
                            cursor.execute(sql, (session_end,
                                                 session_id
                                                 )                                     
                                           )
                            
                            warnings = cursor.fetchwarnings()
                            if warnings:
                                for warning in warnings:
                                    logger.warning(warning)
                            
                            self.db.commit()
                            ret_val = True
                    except Exception as e:
                        logger.error(f"Error updating session: {e}. Could not record close session per token={session_id} in DB")
                        ret_val = False
    
            self.close_connection(caller_name=fname) # make sure connection is closed

        return ret_val

    def get_productbase_data(self):
        """
        Load the journal book and video product data
        """
        fname = "get_productbase_data"
        ret_val = {}
        self.open_connection(caller_name=fname) # make sure connection is open
        if self.db is not None:
            with closing(self.db.cursor(buffered=True, dictionary=True)) as curs:
                sql = "SELECT * from vw_api_sourceinfodb where active>0;" # 1=Active 0=Not Active 2=future
                curs.execute(sql)
                warnings = curs.fetchwarnings()
                if warnings:
                    for warning in warnings:
                        logger.warning(warning)
                        
                row_count = curs.rowcount
                if row_count:
                    sourceData = curs.fetchall()
                    ret_val = sourceData
        else:
            logger.fatal("Connection not available to database.")

        self.close_connection(caller_name=fname) # make sure connection is closed
        return ret_val

    def get_journal_vols(self, source_code=None):
        """
        Load the journal year, vol # Notand doi data
        """
        fname = "get_journal_vols"
        ret_val = {}
        if source_code is not None:
            src_code_clause = f" where src_code RLIKE '{source_code}'"
        else:
            src_code_clause = ""
            
        self.open_connection(caller_name=fname) # make sure connection is open
        if self.db is not None:
            with closing(self.db.cursor(buffered=True, dictionary=True)) as curs:
                sql = f"SELECT * from vw_jrnl_vols {src_code_clause};"
                curs.execute(sql)
                warnings = curs.fetchwarnings()
                if warnings:
                    for warning in warnings:
                        logger.warning(warning)
                        
                row_count = curs.rowcount
                if row_count:
                    ret_val = curs.fetchall()
        else:
            logger.fatal("Connection not available to database.")

        self.close_connection(caller_name=fname) # make sure connection is closed
        return ret_val
        
    def get_user_errormsg_data(self):
        """
        Load the user errormsg data
        """
        fname = "get_user_errormsg_data"
        ret_val = {}
        self.open_connection(caller_name=fname) # make sure connection is open
        if self.db is not None:
            with closing(self.db.cursor(buffered=True, dictionary=True)) as curs:
                sql = f"SELECT * from vw_api_messages;"
                curs.execute(sql)
                warnings = curs.fetchwarnings()
                if warnings:
                    for warning in warnings:
                        logger.warning(warning)
                        
                row_count = curs.rowcount
                if row_count:
                    ret_val = curs.fetchall()
        else:
            logger.fatal("Connection not available to database.")

        self.close_connection(caller_name=fname) # make sure connection is closed
        return ret_val

    def get_article_year(self, doc_id):
        """
        Load the article data for a document id
        """
        fname = "get_productbase_data"
        ret_val = None
        self.open_connection(caller_name=fname) # make sure connection is open
        if self.db is not None:
            with closing(self.db.cursor(buffered=True, dictionary=True)) as curs:
                sql = f"SELECT art_year from api_articles where art_id='{doc_id}';"
                curs.execute(sql)
                row_count = curs.rowcount
                if row_count:
                    sourceData = curs.fetchall()
                    ret_val = sourceData[0]["art_year"]
                else:
                    logger.fatal("Connection not available to database.")
        else:
            logger.error("Connection not available to database.")

        self.close_connection(caller_name=fname) # make sure connection is closed
        return ret_val
        
    def most_viewed_generator( self,
                               publication_period: int=5,  # Number of publication years to include (counting back from current year, 0 means current year)
                               viewperiod: int=4,          # used here for sort and limiting viewcount results (more_than_clause)
                               viewcount: int=None,        # cutoff at this minimum number of views for viewperiod column
                               author: str=None,
                               title: str=None,
                               source_name: str=None,
                               source_code: str=None, 
                               source_type: str="journals", # 'journal', 'book', 'videostream'} standard vals, can abbrev to 1 char or more
                               select_clause: str=opasConfig.VIEW_MOSTVIEWED_DOWNLOAD_COLUMNS, 
                               limit: int=None,
                               offset=0,
                               sort=None, #  can be None (default sort), False (no sort) or a column name + ASC || DESC
                               session_info=None
                               ):
        """
        Return records which are the most viewed for the viewperiod
           restricted to documents published in the publication_period (prev years)
           
        Reinstated here because equivalent from Solr is too slow when fetching the whole set.

           ---------------------
           view_stat_most_viewed
           ---------------------
            SELECT
                `vw_stat_docviews_crosstab`.`document_id` AS `document_id`,
                `vw_stat_docviews_crosstab`.`last_viewed` AS `last_viewed`,
                COALESCE ( `vw_stat_docviews_crosstab`.`lastweek`, 0 ) AS `lastweek`,
                COALESCE ( `vw_stat_docviews_crosstab`.`lastmonth`, 0 ) AS `lastmonth`,
                COALESCE ( `vw_stat_docviews_crosstab`.`last6months`, 0 ) AS `last6months`,
                COALESCE ( `vw_stat_docviews_crosstab`.`last12months`, 0 ) AS `last12months`,
                COALESCE ( `vw_stat_docviews_crosstab`.`lastcalyear`, 0 ) AS `lastcalyear`,
                `api_articles`.`art_auth_citation` AS `hdgauthor`,
                `api_articles`.`art_title` AS `hdgtitle`,
                `api_articles`.`src_title_abbr` AS `srctitleseries`,
                `api_articles`.`bk_publisher` AS `publisher`,
                `api_articles`.`src_code` AS `jrnlcode`,
                `api_articles`.`art_year` AS `pubyear`,
                `api_articles`.`art_vol` AS `vol`,
                `api_articles`.`art_pgrg` AS `pgrg`,
                `api_productbase`.`pep_class` AS `source_type`,
                `api_articles`.`preserve` AS `preserve`,
                `api_articles`.`filename` AS `filename`,
                `api_articles`.`bk_title` AS `bktitle`,
                `api_articles`.`bk_info_xml` AS `bk_info_xml`,
                `api_articles`.`art_citeas_xml` AS `xmlref`,
                `api_articles`.`art_citeas_text` AS `textref`,
                `api_articles`.`art_auth_mast` AS `authorMast`,
                `api_articles`.`art_issue` AS `issue`,
                `api_articles`.`last_update` AS `last_update` 
            FROM
            (  (
                `vw_stat_docviews_crosstab`
                   JOIN `api_articles` ON ((
                           `api_articles`.`art_id` = `vw_stat_docviews_crosstab`.`document_id` ))
                )
               LEFT JOIN `api_productbase` ON ((
                   `api_articles`.`src_code` = `api_productbase`.`pepcode` 
                ))
            )

            viewperiod = 0: lastcalendaryear
                         1: lastweek
                         2: lastmonth
                         3: last6months
                         4: last12months                                
                         
         
         Using the opascentral api_docviews table data, as dynamically statistically aggregated into
           the view vw_stat_most_viewed return the most downloaded (viewed) Documents
           
         1) Using documents published in the last 5, 10, 20, or all years.
            Viewperiod takes an int and covers these or any other period (now - viewPeriod years).
         2) Filtering videos, journals, books, or all content.  source_type filters this.
            Can be: "journals", "books", "videos", or "all" (default)
         3) Optionally filter for author, title, or specific journal.
            Per whatever the caller specifies in parameters.
         4) show views in last 7 days, last month, last 6 months, last calendar year.
            This function returns them all.
         
        """
        fname = "get_most_viewed_table"
        self.open_connection(caller_name=fname) # make sure connection is open
        # get selected view_col_name used for sort and limiting results (more_than_clause)
        view_col_name = opasConfig.VALS_VIEWPERIODDICT_SQLFIELDS.get(viewperiod, "last12months")

        if limit is not None:
            limit_clause = f"LIMIT {offset}, {limit}"
        else:
            limit_clause = ""
            
        if self.db != None:
            if sort is None or sort == True:
                sort_by_clause = f" ORDER BY {view_col_name} DESC"
            elif sort == False:
                sort_by_clause = ""
            else:
                sort_by_clause = f"ORDER BY {sort}"
            
            if publication_period is not None:
                if str(publication_period).upper() == "ALL" or str(publication_period).upper()=="ALLTIME":
                    publication_period = 1000 # should cover most/all time of published writings!
                pub_year_clause = f" AND `pubyear` >= YEAR(NOW()) - {publication_period}"  
            else:
                pub_year_clause = ""

            if source_code is not None:
                source_code_clause = f" AND source_code = '{source_code}'" 
            else:
                source_code_clause = ""

            if source_name is not None:
                source_name = re.sub("[^\.]\*", ".*", source_name, flags=re.IGNORECASE)
                journal_clause = f" AND srctitleseries rlike '{source_name}'" 
            else:
                journal_clause = ""
            
            if source_type == "journals":
                doc_type_clause = f" AND source_code NOT IN {opasConfig.ALL_EXCEPT_JOURNAL_CODES}" 
            elif source_type == "books":
                doc_type_clause = f" AND source_code IN {opasConfig.BOOK_CODES_ALL}"
            elif source_type == "videos":
                doc_type_clause = f" AND source_code IN {opasConfig.VIDOSTREAM_CODES_ALL}"
            else:
                doc_type_clause = ""  # everything

            if author is not None:
                author = re.sub("[^\.]\*", ".*", author, flags=re.IGNORECASE)
                author_clause = f" AND hdgauthor rlike '{author}'"
            else:
                author_clause = ""
                
            if title is not None:
                # glob to re pattern
                # title = re.sub("[^\.]\*", ".*", title, flags=re.IGNORECASE)
                title = re.sub("[^\.]\*", ".*", title, flags=re.IGNORECASE)
                title_clause = f" AND hdgtitle rlike '{title}'"
            else:
                title_clause = ""

            if viewcount is not None:
                more_than_clause = f" AND {view_col_name} > {viewcount}"
            else:
                more_than_clause = ""
            
            # select_clause = "textref, lastweek, lastmonth, last6months, last12months, lastcalyear"
            # Note that WHERE 1 = 1 is used since clauses all start with AND
            sql = f"""SELECT DISTINCT {select_clause} 
                      FROM vw_stat_most_viewed
                      WHERE 1 = 1
                      {doc_type_clause}
                      {author_clause}
                      {more_than_clause}
                      {title_clause}
                      {source_code_clause}
                      {journal_clause}
                      {pub_year_clause}
                      {sort_by_clause}
                      {limit_clause}
                    """
            with closing(self.db.cursor(buffered=True, dictionary=True)) as cursor:
                cursor.execute(sql)
                if cursor.rowcount:
                    for row in cursor:
                        yield row
                
        self.close_connection(caller_name=fname) # make sure connection is closed

    def SQLSelectGenerator(self, sql, use_dict=True):
        #execute a select query and return results as a generator
        #error handling code removed
        fname = "SQLSelectGenerator"
        self.open_connection(caller_name=fname) # make sure connection is open
        if use_dict:
            with closing(self.db.cursor(self.db.cursor(buffered=True, dictionary=True))) as cursor:
                cursor.execute(sql)
                if cursor.rowcount:
                    for row in cursor:
                        yield row
        else:
            with closing(self.db.cursor()) as cursor:
                cursor.execute(sql)
                if cursor.rowcount:
                    for row in cursor:
                        yield row

        self.close_connection(caller_name=fname) # make sure connection is open
    
    def most_cited_generator( self,
                              publication_period = None, # Limit the considered pubs to only those published in these years
                              cited_in_period:str=None,  # Has to be cited more than this number of times, a large nbr speeds the query
                              citecount: int=None,              
                              author: str=None,
                              title: str=None,
                              source_name: str=None,  
                              source_code: str=None,
                              source_type: str=None,
                              select_clause: str=opasConfig.VIEW_MOSTCITED_DOWNLOAD_COLUMNS, 
                              limit: int=None,
                              offset: int=0,
                              sort=None #  can be None (default sort), False (no sort) or a column name + ASC || DESC
                              ):
        """
        Return records which are the most cited for the cited_in_period
           restricted to documents published in the publication_period (prev years)

        Reinstated because downloading from Solr is too slow!
         
        ------------------------------------
         vw_stat_cited_crosstab_with_details
        ------------------------------------
         
         SELECT
            `vw_stat_cited_crosstab`.`cited_document_id` AS `cited_document_id`,
            `vw_stat_cited_crosstab`.`count5` AS `count5`,
            `vw_stat_cited_crosstab`.`count10` AS `count10`,
            `vw_stat_cited_crosstab`.`count20` AS `count20`,
            `vw_stat_cited_crosstab`.`countAll` AS `countAll`,
            `api_articles`.`art_auth_citation` AS `hdgauthor`,
            `api_articles`.`art_title` AS `hdgtitle`,
            `api_articles`.`src_title_abbr` AS `srctitleseries`,
            `api_articles`.`src_code` AS `source_code`,
            `api_articles`.`art_year` AS `year`,
            `api_articles`.`art_vol` AS `vol`,
            `api_articles`.`art_pgrg` AS `pgrg`,
            `api_articles`.`art_id` AS `art_id`,
            `api_articles`.`art_citeas_text` AS `art_citeas_text` 
         FROM
            (
                `vw_stat_cited_crosstab`
                JOIN `api_articles` ON ((
                        `vw_stat_cited_crosstab`.`cited_document_id` = `api_articles`.`art_id` 
                    ))) 
         ORDER BY
            `vw_stat_cited_crosstab`.`countAll` DESC
         
        """
        fname = "most_cited_generator"
        self.open_connection(caller_name=fname) # make sure connection is open
        cited_in_period = opasConfig.normalize_val(cited_in_period, opasConfig.VALS_YEAROPTIONS, default='ALL')
        
        if limit is not None:
            limit_clause = f"LIMIT {offset}, {limit}"
        else:
            limit_clause = ""
            
        if self.db != None:
            if sort is None or sort == True:
                sort_by_clause = f"ORDER BY count{cited_in_period} DESC"
            elif sort == False:
                sort_by_clause = ""
            else:
                sort_by_clause = f"ORDER BY {sort}"
        
            
            start_year = dtime.date.today().year
            if publication_period == "All":
                publication_period = dtime.date.today().year

            if publication_period is None:
                start_year = None
            else:
                start_year -= publication_period
                start_year = f">{start_year}"
                
            #TODO which one, before code, or after code?
            if publication_period is not None:
                pub_year_clause = f" AND `year` >= YEAR(NOW()) - {publication_period}"  # consider only the past viewPeriod years
            else:
                pub_year_clause = ""
            
            if source_name is not None:
                source_name = re.sub("[^\.]\*", ".*", source_name, flags=re.IGNORECASE)
                journal_clause = f" AND srctitleseries rlike '{source_name}'" 
            else:
                journal_clause = ""

            if source_code is not None:
                source_code_clause = f" AND source_code = '{source_code}'" 
            else:
                source_code_clause = ""

            if source_type == "journals":
                doc_type_clause = f" AND source_code NOT IN {opasConfig.ALL_EXCEPT_JOURNAL_CODES}" 
            elif source_type == "books":
                doc_type_clause = f" AND source_code IN {opasConfig.BOOK_CODES_ALL}"
            elif source_type == "videos":
                doc_type_clause = f" AND source_code IN {opasConfig.VIDEOSTREAM_CODES_ALL}"
            else:
                doc_type_clause = ""  # everything

            if author is not None:
                # author = fnmatch.translate(author)
                author = re.sub("[^\.]\*", ".*", author, flags=re.IGNORECASE)
                author_clause = f" AND hdgauthor rlike '{author}'"
            else:
                author_clause = ""
                
            if title is not None:
                # glob to re pattern
                title = re.sub("[^\.]\*", ".*", title, flags=re.IGNORECASE)
                # title = fnmatch.translate(title)
                title_clause = f" AND hdgtitle rlike '{title}'"
            else:
                title_clause = ""

            if citecount is not None:
                more_than_clause = f" AND count{cited_in_period} > {citecount}"
            else:
                more_than_clause = ""
                
            # Note that WHERE 1 = 1 is used since clauses all start with AND
            sql = f"""SELECT DISTINCT {select_clause} 
                      FROM vw_stat_cited_crosstab_with_details
                      WHERE 1 = 1
                      {doc_type_clause}
                      {author_clause}
                      {more_than_clause}
                      {title_clause}
                      {journal_clause}
                      {pub_year_clause}
                      {sort_by_clause}
                      {limit_clause}
                    """

            with closing(self.db.cursor(buffered=True, dictionary=True)) as cursor:
                cursor.execute(sql)
                if cursor.rowcount:
                    for row in cursor:
                        #print (f"Row: ({row})")
                        yield row

        # print ("Closing connection in generator")
        self.close_connection(caller_name=fname) # make sure connection is closed

    def get_citation_counts(self) -> dict:
        """
         Using the opascentral vw_stat_cited_crosstab view, based on the api_biblioxml which is used to detect citations,
           return the cited counts for each art_id
           
           Primary view definition copied here for safe keeping.
           ----------------------
           vw_stat_cited_crosstab
           ----------------------
           
           SELECT
           `r0`.`cited_document_id` AS `cited_document_id`,
           any_value (
           COALESCE ( `r1`.`count5`, 0 )) AS `count5`,
           any_value (
           COALESCE ( `r2`.`count10`, 0 )) AS `count10`,
           any_value (
           COALESCE ( `r3`.`count20`, 0 )) AS `count20`,
           any_value (
           COALESCE ( `r4`.`countAll`, 0 )) AS `countAll` 
           FROM
               (((((
                               SELECT DISTINCT
                                   `api_biblioxml`.`art_id` AS `articleID`,
                                   `api_biblioxml`.`bib_local_id` AS `internalID`,
                                   `api_biblioxml`.`full_ref_xml` AS `fullReference`,
                                   `api_biblioxml`.`bib_rx` AS `cited_document_id` 
                               FROM
                                   `api_biblioxml` 
                                   ) `r0`
                               LEFT JOIN `vw_stat_cited_in_last_5_years` `r1` ON ((
                                       `r1`.`cited_document_id` = `r0`.`cited_document_id` 
                                   )))
                           LEFT JOIN `vw_stat_cited_in_last_10_years` `r2` ON ((
                                   `r2`.`cited_document_id` = `r0`.`cited_document_id` 
                               )))
                       LEFT JOIN `vw_stat_cited_in_last_20_years` `r3` ON ((
                               `r3`.`cited_document_id` = `r0`.`cited_document_id` 
                           )))
                   LEFT JOIN `vw_stat_cited_in_all_years` `r4` ON ((
                           `r4`.`cited_document_id` = `r0`.`cited_document_id` 
                       ))) 
           WHERE
               ((
                       `r0`.`cited_document_id` IS NOT NULL 
                       ) 
                   AND ( `r0`.`cited_document_id` != 'None' ) 
                   AND (
                   substr( `r0`.`cited_document_id`, 1, 3 ) NOT IN ( 'ZBK', 'IPL', 'SE.', 'GW.' ))) 
           GROUP BY
               `r0`.`cited_document_id` 
           ORDER BY
               `countAll` DESC
           
        """
        fname = "get_citation_counts"
        citation_table = []
        print ("Collecting citation counts from cross-tab in biblio database...this will take a minute or two...")
        try:
            self.open_connection(caller_name=fname)
            # Get citation lookup table
            try:
                with closing(self.db.cursor(buffered=True, dictionary=True)) as cursor:
                    sql = """
                          SELECT cited_document_id, count5, count10, count20, countAll from vw_stat_cited_crosstab; 
                          """
                    cursor.execute(sql)
                    if cursor.rowcount:
                        citation_table = cursor.fetchall()
                    else:
                        logger.error("Cursor execution failed.  Can't fetch citation counts.")
                    
            except MemoryError as e:
                logger.error("Memory error loading table: {}".format(e))
            except Exception as e:
                logger.error("Table Query Error: {}".format(e))
            
            self.close_connection(caller_name=fname)
            
        except Exception as e:           
            logger.error("Database Connect Error: {}".format(e))
            citation_table["dummy"] = None
        
        return citation_table

    def get_most_viewed_crosstab(self, limit=None, offset=None):
        """
         Using the opascentral api_docviews table data, as dynamically statistically aggregated into
           the view vw_stat_most_viewed return the most downloaded (viewed) documents
           
         Returns 0,[] if no rows are returned
         
         Supports the updates to Solr via solrXMLPEPWebload, used for view count queries.
            
        """
        ret_val = []
        row_count = 0
        limit_str = ""
        if limit is not None:
            limit_str = f" LIMIT {limit}"
            if offset is not None:
                limit_str = f"{limit_str}, {offset}"

        # always make sure we have the right input value
        try:
            self.open_connection(caller_name="get_most_viewed_crosstab") # make sure connection is open
            
            if self.db is not None:
                with closing(self.db.cursor(buffered=True, dictionary=True)) as cursor:
                    try:
                        sql = f"""SELECT DISTINCTROW * FROM vw_stat_docviews_crosstab{limit_str}"""
                        success = cursor.execute(sql)
                        if success:
                            ret_val = cursor.fetchall() # returns empty list if no rows
                        else:
                            logger.error("Cursor execution failed.  Can't fetch most_viewed_crosstab.")
                    except Exception as e:
                        logger.error(f"Error {e}. Cursor execution failed.  Can't fetch most_viewed_crosstab.")
            else:
                logger.error("Connection not available to database.")
        
            self.close_connection(caller_name="get_most_downloaded_crosstab") # make sure connection is closed
            
        except Exception as e:           
            logger.error("Database Connect Error: {}".format(e))
            
        row_count = len(ret_val)
        return row_count, ret_val

    def get_select_count(self, sqlSelect: str):
        """
        Generic retrieval from database, just the count
        
        >>> ocd = opasCentralDB()
        >>> count = ocd.get_select_count(sqlSelect="SELECT * from vw_reports_user_searches;")
        >>> count > 1000
        True
        
        """
        self.open_connection(caller_name="get_select_count") # make sure connection is open
        ret_val = None

        sqlSelect = re.sub("SELECT .+? FROM", "SELECT COUNT(*) AS FULLCOUNT FROM", sqlSelect, count=1, flags=re.IGNORECASE)
        try:
            if self.db is not None:
                with closing(self.db.cursor(buffered=True, dictionary=True)) as cursor:
                    cursor.execute(sqlSelect)
                    row = cursor.fetchall()
                    ret_val = row[0]["FULLCOUNT"]
            else:
                logger.error("Connection not available to database.")

        except Exception as e:
            logger.error("Can't retrieve count.")
            ret_val = 0
            
        self.close_connection(caller_name="get_select_count") # make sure connection is closed

        # return session model object
        return ret_val # None or Session Object
               
    def get_articles_newer_than(self, days_back=7):
        """
        Return list of articles newer than the current date - days_back.
       
        >>> ocd = opasCentralDB()
        >>> articles = ocd.get_articles_newer_than(days_back=14) 
        >>> len(articles) > 1
        True

        """
        fname = "get_articles_newer_than"
        self.open_connection(caller_name=fname) # make sure connection is open
        ret_val = []
        # newer_than = datetime.utcfromtimestamp(newer_than_date).strftime(opasConfig.TIME_FORMAT_STR)
        def_date = datetime.now() - dtime.timedelta(days=days_back)
        newer_than_date = def_date.strftime('%Y-%m-%d %H:%M:%S')
        self.db.ping()
        sqlSelect = """
                        SELECT art_id FROM article_tracker
                        WHERE date_inserted > date(%s)
        """
        if self.db is not None:
            errmsg = f"getting articles newer than {days_back} days back, date {newer_than_date}"
            with closing(self.db.cursor(buffered=True, dictionary=True)) as cursor:
                try:
                    cursor.execute(sqlSelect, (newer_than_date, ))
                except ValueError as e:
                    logger.error(f"DB Value Error {e} - {errmsg}")
                except mysql.connector.IntegrityError as e:
                    logger.error(f"Integrity Error {e} - {errmsg}")
                except mysql.connector.InternalError as e:
                    logger.error(f"Internal Error {e} - {errmsg}")
                except mysql.connector.DatabaseError as e:
                    logger.error(f"Database Error {e} - {errmsg}")
                except Exception as e:
                    logger.error(f"DB Error  {e} - {errmsg}")
                else:
                    records = cursor.fetchall()
                    # fix 2021-09-08, None returned in some cases, but not iterable.
                    if records is not None:
                        ret_val = [a['art_id'] for a in records]
                    else:
                        ret_val = []
                    
            self.close_connection(caller_name=fname) # make sure connection is closed
        else:
            logger.warning(f"RDS DB was not successfully opened ({caller_name}). WhatsNew check skipped.")

        # return session model object
        return ret_val # List of records or empty list

    def get_min_max_volumes(self, source_code):
        sel = f"""
                SELECT `api_articles`.`src_code` AS `src_code`,
                       min( `api_articles`.`art_vol` ) AS `min`,
                       max( `api_articles`.`art_vol` ) AS `max` 
                FROM
                    `api_articles`
                WHERE src_code = '{source_code}'
                GROUP BY
                    `api_articles`.`src_code`
		"""
        fname = "get_min_max_volumes"
        self.open_connection(caller_name=fname) # make sure connection is open
        ret_val = None
        if self.db is not None:
            try:
                with closing(self.db.cursor(buffered=True, dictionary=True)) as cursor:
                    try:
                        cursor.execute(sel)
                    except ValueError as e:
                        logger.error(f"DB Value Error {e} - {errmsg}")
                    except mysql.connector.IntegrityError as e:
                        logger.error(f"Integrity Error {e} - {errmsg}")
                    except mysql.connector.InternalError as e:
                        logger.error(f"Internal Error {e} - {errmsg}")
                    except mysql.connector.DatabaseError as e:
                        logger.error(f"Database Error {e} - {errmsg}")
                    except Exception as e:
                        logger.error(f"DB Error  {e} - {errmsg}")
                    else:
                        ret_val = cursor.fetchall()
            except Exception as e:
                logger.error(f"DB Error {e}")

        self.close_connection(caller_name=fname) # make sure connection is closed

        try:
            ret_val = ret_val[0]
            ret_val["infosource"] = "volumes_min_max"
        except Exception as e:
            ret_val = None
            
        return ret_val

    def get_select_as_list_of_dicts(self, sqlSelect: str):
        """
        Generic retrieval from database, into dict
        
        >>> ocd = opasCentralDB()
        >>> rows = ocd.get_select_as_list_of_dicts(sqlSelect="SELECT * from vw_reports_session_activity;")
        >>> len(rows) >= 1
        True
        >>> type(rows[0]) == dict
        True
        """
        fname = "get_selection_as_list_of_dicts"
        self.open_connection(caller_name=fname) # make sure connection is open
        ret_val = None
        if self.db is not None:
            # rows = self.SQLSelectGenerator(sqlSelect)
            curs = self.db.cursor(buffered=True, dictionary=True)
            curs.execute(sqlSelect)
            warnings = curs.fetchwarnings()
            if warnings:
                for warning in warnings:
                    logger.warning(warning)
                    
            ret_val = [row for row in curs.fetchall()]
            #ret_val = [model(row=row) for row in rows]
            
        self.close_connection(caller_name=fname) # make sure connection is closed

        # return session model object
        return ret_val # None or Session Object
        
    #------------------------------------------------------------------------------------------------------
    def get_select_as_list_of_models(self, sqlSelect: str, model, model_type="Structured"):
        """
        Generic retrieval from database, into dict
        
        if model is explicit, i.e., not a generic dict, this works: 
            ret_val = [model(**row) for row in rows]
        if model is a dict (generic) this works
            ret_val = [model(row=row) for row in rows]

        Not sure why!  But only call this with a generic dict based model
        
        >>> ocd = opasCentralDB()
        >>> records = ocd.get_select_as_list_of_models(sqlSelect="SELECT * from vw_reports_session_activity;", model=models.ReportListItem)
        >>> len(records) > 1
        True
        >>> type(records[0]) == models.ReportListItem
        True
        """
        fname = "get_selection_as_list_of_models"
        self.open_connection(caller_name=fname) # make sure connection is open
        ret_val = None
        if self.db is not None:
            # rows = self.SQLSelectGenerator(sqlSelect)
            curs = self.db.cursor(buffered=True, dictionary=True)
            curs.execute(sqlSelect)
            warnings = curs.fetchwarnings()
            if warnings:
                for warning in warnings:
                    logger.warning(warning)
            rows = curs.fetchall()
            if model_type == "Generic":
                ret_val = [model(row=row) for row in rows]
            else: # structured
                ret_val = [model(**row) for row in rows]
                
        self.close_connection(caller_name=fname) # make sure connection is closed

        # return session model object
        return ret_val # None or Session Object
        
    #------------------------------------------------------------------------------------------------------
    def get_references_from_biblioxml_table(self, article_id, ref_local_id=None, verbose=None):
        """
        Return a list of references from the api_biblioxml table in opascentral
        """
        ret_val = None

        if ref_local_id is not None:
            local_id_clause = f"AND bib_local_id RLIKE '{ref_local_id}'"
        else:
            local_id_clause = ""
            
        select = f"""SELECT * from api_biblioxml
                     WHERE art_id = '{article_id}' {local_id_clause}
                     """
    
        results = self.get_select_as_list_of_models(select, model=models.Biblioxml)
        
        ret_val = results
    
        return ret_val  # return True for success

    #------------------------------------------------------------------------------------------------------
    def get_select_as_list(self, sqlSelect: str):
        """
        Generic retrieval from database
        
        >>> ocd = opasCentralDB()
        >>> records = ocd.get_select_as_list(sqlSelect="SELECT * from vw_reports_session_activity;")
        >>> len(records) > 1
        True
        >>> type(records[0]) == tuple
        True
        """
        fname = "get_selection_as_list"
        self.open_connection(caller_name=fname) # make sure connection is open
        ret_val = None
        if self.db is not None:
            # don't use dicts here
            # ret_val = self.SQLSelectGenerator(sqlSelect, use_dict=False)
            with closing(self.db.cursor(buffered=True, dictionary=False)) as curs:
                curs.execute(sqlSelect)
                warnings = curs.fetchwarnings()
                if warnings:
                    for warning in warnings:
                        logger.warning(warning)
                
                ret_val = curs.fetchall()
            
        self.close_connection(caller_name=fname) # make sure connection is closed

        # return session model object
        return ret_val # None or Session Object

    def get_session_from_db(self, session_id):
        """
        Get the session record info for session sessionID
        
        Tested in main instance docstring
        """
        fname = "get_session_from_db"
        from models import SessionInfo # do this here to avoid circularity
        self.open_connection(caller_name=fname) # make sure connection is open
        ret_val = None
        if self.db is not None:
            try:
                self.db.ping()
                with closing(self.db.cursor(buffered=True, dictionary=True)) as cursor:
                    # now insert the session
                    sql = f"SELECT * FROM api_sessions WHERE session_id = '{session_id}'";
                    cursor.execute(sql)
                    if cursor.rowcount:
                        session = cursor.fetchone()
                        try:
                            if session["username"] is None:
                                session["username"] = opasConfig.USER_NOT_LOGGED_IN_NAME
                        except Exception as e:
                            session["username"] = opasConfig.USER_NOT_LOGGED_IN_NAME
                            logger.error(f"Username is None. {e}")
        
                        # sessionRecord
                        ret_val = SessionInfo(**session)
                    else:
                        ret_val = None
                        logger.debug(f"{fname} - Session info not found in db {session_id}")
                        
            except mysql.connector.DataError as e:
                logger.error(f"DBError {fname}. Data Error {e} ({session_id})")
            except mysql.connector.OperationalError as e:
                logger.error(f"DBError {fname}. Operation Error {e} ({session_id})")
            except mysql.connector.IntegrityError as e:
                logger.error(f"DBError {fname}. Integrity Error {e} ({session_id})")
            except mysql.connector.InternalError as e:
                logger.error(f"DBError {fname}. Internal Error {e} ({session_id})")
            except mysql.connector.ProgrammingError as e:
                logger.error(f"DBError {fname}. Programming Error {e} ({session_id})")
            except mysql.connector.NotSupportedError as e:
                logger.error(f"DBError {fname}. Feature Not Supported Error {e} ({session_id})")
            except Exception as e:
                logger.error(f"DBError{fname}. Exception: %s" % (e))
                
        self.close_connection(caller_name=fname) # make sure connection is closed

        # return session model object
        return ret_val # None or Session Object

    def get_mysql_version(self):
        """
        Get the mysql version number
        
        >>> ocd = opasCentralDB()
        >>> ocd.get_mysql_version()
        'Vers: ...'
        """
        fname = "update_session"
        ret_val = "Unknown"
        self.open_connection(caller_name=fname) # make sure connection is open
        if self.db is not None:
            with closing(self.db.cursor()) as cursor:
                try:
                    sql = "SELECT VERSION();"
                    cursor.execute(sql)
                    ret_val = "Vers: " + cursor.fetchone()[0]
                except Exception as e:
                    logging.debug(f"MySQL Version Fetch Error: {e}")
                    ret_val = None
        else:
            logger.fatal("Connection not available to database.")

        self.close_connection(caller_name=fname) # make sure connection is closed
        return ret_val
    
    def get_update_date_database(self):
        """
        Return isoformatted date/time of last database update based on article_tracker or ""
          if not found.
       
        >>> ocd = opasCentralDB()
        >>> ret = ocd.get_update_date_database() 

        """
        fname = "get_articles_newer_than"
        self.open_connection(caller_name=fname) # make sure connection is open
        ret_val = []
        # newer_than = datetime.utcfromtimestamp(newer_than_date).strftime(opasConfig.TIME_FORMAT_STR)
        sqlSelect = "SELECT max(date_inserted) as db_update_date FROM article_tracker"
        if self.db is not None:
            errmsg = f"getting database update date"
            with closing(self.db.cursor(buffered=True, dictionary=True)) as cursor:
                try:
                    cursor.execute(sqlSelect)
                except ValueError as e:
                    logger.error(f"DB Value Error {e} - {errmsg}")
                except mysql.connector.IntegrityError as e:
                    logger.error(f"Integrity Error {e} - {errmsg}")
                except mysql.connector.InternalError as e:
                    logger.error(f"Internal Error {e} - {errmsg}")
                except mysql.connector.DatabaseError as e:
                    logger.error(f"Database Error {e} - {errmsg}")
                except Exception as e:
                    logger.error(f"DB Error  {e} - {errmsg}")
                else:
                    record = cursor.fetchone()
                    if record is not None:
                        ret_val = record['db_update_date']
                        ret_val = ret_val.isoformat()
                    else:
                        ret_val = ""
                    
            self.close_connection(caller_name=fname) # make sure connection is closed
        else:
            logger.warning(f"RDS DB was not successfully opened ({caller_name}). WhatsNew check skipped.")

        # return session model object
        return ret_val # List of records or empty list

    def update_session(self,
                       session_id,
                       api_client_id, 
                       userID=None,
                       username=None,
                       usertype=None,
                       hassubscription=None, 
                       authenticated: int=None,
                       validusername=None, 
                       authorized_peparchive: int=None,
                       authorized_pepcurrent: int=None,
                       session_end=None,
                       api_direct_login=None, 
                       userIP=None):
        """
        Update the extra fields in the session record
        """
        fname = "update_session"
        ret_val = False
        self.open_connection(caller_name=fname) # make sure connection is open
        setClause = "SET "
        added = 0
        if api_client_id is not None:
            setClause += f" api_client_id = '{api_client_id}'"
            added += 1
        if userID is not None:
            if added > 0:
                setClause += ", "
            setClause += f" user_id = '{userID}'"
            added += 1
        if username is not None:
            if added > 0:
                setClause += ", "
            setClause += f" username = '{username}'"
            added += 1
        if usertype is not None:
            if added > 0:
                setClause += ", "
            setClause += f" user_type = '{usertype}'"
            added += 1
            if usertype == opasConfig.ADMIN_TYPE and authenticated:
                if added > 0:
                    setClause += ", "
                setClause += f" admin = 1"
                added += 1
        if hassubscription is not None:
            if added > 0:
                setClause += ", "
            setClause += f" has_subscription = '{hassubscription}'"
            added += 1
        if authenticated:
            if added > 0:
                setClause += ", "
            setClause += f" authenticated = '{authenticated}'"
            added += 1
            if added > 0:
                setClause += ", "
            setClause += f" is_valid_login = '{authenticated}'"
            added += 1
        if validusername:
            if added > 0:
                setClause += ", "
            setClause += f" is_valid_username = '{validusername}'"
            added += 1
        if authorized_peparchive:
            if added > 0:
                setClause += ", "
            setClause += f" authorized_peparchive = '{authorized_peparchive}'"
            added += 1
        if authorized_pepcurrent:
            if added > 0:
                setClause += ", "
            setClause += f" authorized_pepcurrent = '{authorized_pepcurrent}'"
            added += 1
        if api_direct_login is not None:
            if added > 0:
                setClause += ", "
            setClause += f" api_direct_login = '{api_direct_login}'"
            added += 1
        if session_end is not None:
            if added > 0:
                setClause += ", "
            setClause += " session_end = '{}'".format(session_end) 
            added += 1

        if added > 0:
            if self.db is not None:
                with closing(self.db.cursor()) as cursor:
                    try:
                        sql = """UPDATE api_sessions
                                 {}
                                 WHERE session_id = %s
                              """.format(setClause)
                        cursor.execute(sql, (session_id, )) # was getting error in debug without ',' as routine saw string rather than list/tuple.
                        warnings = cursor.fetchwarnings()
                        if warnings:
                            for warning in warnings:
                                logger.warning(warning)
                        ret_val = True
                        logger.debug(f"Updated session record for session: {session_id}")
                    except mysql.connector.InternalError as error:
                        code, message = error.args
                        logger.error(code, message)
                        ret_val = False 
                    except mysql.connector.Error as error:
                        logger.error(code, message)
                        ret_val = False
                    except Exception as e:
                        message = f"General exception saving to database: {e}"
                        logger.error(message)
                        ret_val = False
                    else:
                        self.db.commit()

        self.close_connection(caller_name=fname) # make sure connection is closed
        if ret_val == False:
            logger.debug(f"Could not record close session per sessionID {session_id} in DB")
            
        return ret_val

    def delete_session(self, session_id):
        """
        Remove the session record, mostly for testing purposes.
        
        """
        ret_val = False
        #session = None
        if session_id is None:
            err_msg = "Parameter error: No session ID specified"
            logger.error(err_msg)
        else:
            if not self.open_connection(caller_name="delete_session"): # make sure connection opens
                logger.error("Delete session could not open database")
            else: # its open
                if self.db is not None:  # don't need this check, but leave it.
                    with closing(self.db.cursor()) as curs:
                        # now delete the session
                        sql = """DELETE FROM api_sessions
                                 WHERE session_id = '%s'""" % session_id
                        
                        curs.execute(sql)
                        warnings = curs.fetchwarnings()
                        if warnings:
                            for warning in warnings:
                                logger.warning(warning)
                        
                        ret_val = self.db.commit()
    
                    # self.sessionInfo = None
                    self.close_connection(caller_name="delete_session") # make sure connection is closed
                else:
                    logger.fatal("Connection not available to database.")

        return ret_val # return true or false, success or failure
        
    def save_session(self,
                     session_id,
                     session_info: models.SessionInfo=None
                     ):
        """
        Save the session info to the database
        
        Tested in main instance docstring
        """
        fname = "save_session"
        ret_val = False
        if session_id is None:
            logger.error(f"No session ID specified")
        elif session_info is None: # for now, required
            logger.error(f"No session_info specified")
        else:
            if session_info.session_start is None:
                session_info.session_start = datetime.utcfromtimestamp(time.time()).strftime(opasConfig.TIME_FORMAT_STR_DB)
                if opasConfig.DEBUG_TRACE: print (f"{fname} set session Start: {session_info.session_start}")
            if not self.open_connection(caller_name=fname): # make sure connection opens
                logger.error(f"Could not open database")
            else: # its open
                if self.db is not None:  # don't need this check, but leave it.
                    with closing(self.db.cursor()) as cursor:
                        # now insert the session
                        sql = """REPLACE INTO api_sessions(session_id,
                                                           user_id, 
                                                           admin,
                                                           api_client_id,
                                                           authenticated,
                                                           authorized_peparchive,
                                                           authorized_pepcurrent,
                                                           has_subscription,
                                                           is_valid_login,
                                                           is_valid_username,
                                                           username,
                                                           user_type,
                                                           session_start,
                                                           session_end,
                                                           session_expires_time,
                                                           api_direct_login
                )
                VALUES 
                  (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) """ # removed session_info.confirmed_unauthenticated
                        try:
                            cursor.execute(sql, 
                                                     (session_info.session_id, 
                                                      session_info.user_id, 
                                                      session_info.admin, 
                                                      session_info.api_client_id,
                                                      session_info.authenticated,
                                                      session_info.authorized_peparchive,
                                                      session_info.authorized_pepcurrent, 
                                                      session_info.has_subscription, 
                                                      session_info.is_valid_login, 
                                                      session_info.is_valid_username, 
                                                      session_info.username,
                                                      session_info.user_type, 
                                                      session_info.session_start, 
                                                      session_info.session_end, 
                                                      session_info.session_expires_time,
                                                      session_info.api_direct_login
                                                      )
                                                     )
                            warnings = cursor.fetchwarnings()
                            if warnings:
                                for warning in warnings:
                                    logger.warning(warning)
                            success = cursor.rowcount

                        except mysql.connector.IntegrityError as e:
                            success = False
                            logger.error(f"Integrity Error {e}")
                            
                        except Exception as e:
                            success = False
                            logger.error(f"Error: {e}")
                           
                        if success:
                            ret_val = True
                            self.db.commit()
                            logger.debug(f"Saved sessioninfo: {session_info.session_id}")
                        else:
                            msg = f"{session_id} Insert Error. Record Could not be Saved"
                            logger.error(msg)
                            ret_val = False
                        
                    # session_info = self.get_session_from_db(session_id)
                    # self.sessionInfo = session_info
                    self.close_connection(caller_name=fname) # make sure connection is closed
    
        # return session model object
        return ret_val, session_info #True or False, and SessionInfo Object

    #def close_inactive_sessions(self, inactive_time=opasConfig.SESSION_INACTIVE_LIMIT):
        #"""
        #Close any sessions where they've been inactive for inactive_time minutes
        #"""
        #removed 2021-12-07

    def count_open_sessions(self):
        """
        Get a count of any open sessions
        
        >>> ocd = opasCentralDB()
        >>> session_count = ocd.count_open_sessions()

        """
        fname = "count_open_sessions"
        ret_val = 0
        self.open_connection(caller_name=fname) # make sure connection is open

        if self.db is not None:
            try:
                cursor = self.db.cursor()
                sql = """SELECT COUNT(*)
                         FROM api_sessions
                         WHERE session_end is NULL
                      """
                cursor.execute(sql)
                result = cursor.fetchone()
                ret_val = result[0]
                cursor.close()
                    
            except mysql.connector.InternalError as error:
                code, message = error.args
                logger.error(code, message)
            

        self.close_connection(caller_name=fname) # make sure connection is closed
        return ret_val
    
    #def close_expired_sessions(self):
        #"""
        #Close any sessions past the set expiration time set in the record
        
        #>>> ocd = opasCentralDB()
        #>>> numb = ocd.close_expired_sessions()
        #>>> numb >= 0
        #True
        #"""
        #removed 2021-12-07
        
    def record_session_endpoint(self,
                                session_info=None,
                                api_endpoint_id=0,
                                params=None,
                                item_of_interest=None,
                                return_status_code=0,
                                api_endpoint_method="get",
                                status_message=None):
        """
        Track endpoint calls
        2020-08-25: Added api_endpoint_method
        
        Tested in main instance docstring
        """
        fname = "record_session_endpoint"
        ret_val = None
        if not self.open_connection(caller_name=fname): # make sure connection is open
            logger.error("record_session_endpoint could not open database")
        else:
            try:
                session_id = session_info.session_id
                client_id = session_info.api_client_id
            except:
                if self.session_id is None:
                    # no session open!
                    logger.error("OCD: No session is open")
                    return ret_val
                else:
                    session_id = self.session_id
                    client_id = opasConfig.NO_CLIENT_ID
                    
            # Workaround for None in session id
            if session_id is None:
                session_id = opasConfig.NO_SESSION_ID # just to record it
                
            if self.db is not None:  # shouldn't need this test
                with closing(self.db.cursor()) as cursor:
                    # TODO: I removed returnStatusCode from here. Remove it from the DB
                    if session_info.authenticated:
                        sql = """INSERT INTO 
                                    api_session_endpoints(session_id, 
                                                          api_endpoint_id,
                                                          params, 
                                                          item_of_interest, 
                                                          return_status_code,
                                                          api_method,
                                                          return_added_status_message
                                                         )
                                                         VALUES 
                                                         (%s, %s, %s, %s, %s, %s, %s)"""
                    else:
                        # TODO: Record in a separate table.
                        sql = """INSERT INTO 
                                    api_session_endpoints_not_logged_in(session_id, 
                                                                        api_endpoint_id,
                                                                        params, 
                                                                        item_of_interest, 
                                                                        return_status_code,
                                                                        api_method,
                                                                        return_added_status_message
                                                                       )
                                                                       VALUES 
                                                                       (%s, %s, %s, %s, %s, %s, %s)"""
    
                    logger.debug(f"Session ID: {session_id} (client {client_id}) accessed Session Endpoint {api_endpoint_id}")
                    try:
                        ret_val = cursor.execute(sql, (session_id, 
                                                       api_endpoint_id, 
                                                       params,
                                                       item_of_interest,
                                                       return_status_code,
                                                       api_endpoint_method, 
                                                       status_message
                                                      ))
                        ret_val = cursor.rowcount
                        self.db.commit()
                    except mysql.connector.IntegrityError as e:
                        logger.error(f"Integrity Error {e} logging endpoint {api_endpoint_id} for session {session_id}.")
                        #session_info = self.get_session_from_db(session_id)
                        #if session_info is None:
                            #self.save_session(session_id) # recover for next time.
                    except Exception as e:
                        logger.error(f"Error logging endpoint {api_endpoint_id} for session {session_id}. Error: {e}")
            
            self.close_connection(caller_name=fname) # make sure connection is closed

        return ret_val

    def get_sources(self, src_code=None, src_type=None, src_name=None, limit=None, offset=0):
        """
        Return a list of sources
          - for a specific source_code
          - OR for a specific source type (e.g. journal, book)
          - OR if source and src_type are not specified, bring back them all
          - OR rlike a src_name (any word(s) within src_name, or can be regex.  Always matches the start and end words")
          
        >>> ocd = opasCentralDB()
        >>> count, resp = ocd.get_sources(src_code='IJP')
        >>> resp[0]["basecode"]
        'IJP'
        >>> count
        1

        >>> ocd = opasCentralDB()
        >>> count, resp = ocd.get_sources(src_type='book')
        >>> count > 98
        True

        # test normalize src_type (req len of input=4, expands to full, standard value)
        >>> ocd = opasCentralDB()
        >>> count, resp = ocd.get_sources(src_type='videos')
        >>> count >= 11
        True

        >>> count, resp = ocd.get_sources(src_name='Psychoanalysis')
        >>> count > 30
        True

        >>> count, resp = ocd.get_sources(src_name='Psychoan.*')
        >>> count >= 33
        True

        >>> count, resp = ocd.get_sources(src_code='IJP', src_name='Psychoanalysis', limit=5)
        >>> resp[0]["basecode"]
        'IJP'
        >>> count
        1

        >>> count, resp = ocd.get_sources()
        >>> count > 188
        True
        
        """
        fname = "get_sources"
        self.open_connection(caller_name=fname) # make sure connection is open
        total_count = 0
        ret_val = None
        limit_clause = ""
        if limit is not None:
            limit_clause = f"LIMIT {limit}"
            if offset != 0:
                limit_clause += f" OFFSET {offset}"

        if self.db is not None:
            src_code_clause = ""
            prod_type_clause = ""
            src_title_clause = ""
            
            try:
                if src_code is not None and src_code != "*":
                    if "*" in src_code:
                        src_code_clause = f"AND basecode rlike '^{src_code}$'"
                    else:
                        src_code_clause = f"AND basecode = '{src_code}'"
                        
                if src_type is not None and src_type != "*":
                    # already normalized, don't do it again
                    # src_type = normalize_val(src_type, opasConfig.VALS_PRODUCT_TYPES)
                    if src_type in ("stream", "videos"):
                        src_type = "videostream"
                    prod_type_clause = f"AND product_type = '{src_type}'"
                if src_name is not None:
                    src_title_clause = f"AND title rlike '(.*\s)?{src_name}(\s.*)?'"

                # 2020-11-13 - changed ref from vw_api_productbase to vw_api_productbase_instance_counts to include instance counts
                sqlAll = f"""FROM vw_api_productbase_instance_counts
                             WHERE active >= 1
                                AND product_type <> 'bookseriessub'
                                {src_code_clause}
                                {prod_type_clause}
                                {src_title_clause}
                             ORDER BY title {limit_clause}"""
                
                with closing(self.db.cursor(buffered=True, dictionary=True)) as curs:
                    sql = "SELECT * " + sqlAll
                    curs.execute(sql)
                    warnings = curs.fetchwarnings()
                    if warnings:
                        for warning in warnings:
                            logger.warning(warning)
                    
                    total_count = curs.rowcount
                    ret_val = curs.fetchall()
                    if limit_clause is not None:
                        # do another query to count
                        with closing(self.db.cursor()) as curs2:
                            sqlCount = "SELECT COUNT(*) " + sqlAll
                            curs2.execute(sqlCount)
                            try:
                                total_count = curs2.fetchone()[0]
                            except:
                                total_count  = 0
            except Exception as e:
                msg = f"Error querying vw_api_productbase_instance_counts: {e}"
                logger.error(msg)
                # print (msg)
            
        self.close_connection(caller_name=fname) # make sure connection is closed

        # return session model object
        return total_count, ret_val # None or Session Object

    def save_client_config(self, client_id:str, client_configuration: models.ClientConfigList, session_id, replace=False):
        """
        Save a client configuration.  Data format is up to the client.
        
        Returns True of False

        >>> ocd = opasCentralDB()
        >>> model = models.ClientConfigList(configList=[models.ClientConfigItem(configName="demo", configSettings={"A":"123", "B":"1234"})])
        >>> ocd.save_client_config(client_id="123", client_configuration=model, session_id="test123", replace=True)
        (200, 'OK')
        >>> model = models.ClientConfigList(configList=[models.ClientConfigItem(configName="test", configSettings={"A":"123", "B":"1234"}), models.ClientConfigItem(configName="test2", configSettings={"C":"456", "D":"5678"})])
        >>> ocd.save_client_config(client_id="123", client_configuration=model, session_id="test123", replace=True)
        (200, 'OK')
        """
        fname = "save_client_config"
        msg = "OK"
        # convert client id to int
        try:
            client_id_int = int(client_id)
        except Exception as e:
            msg = f"Client ID should be a string containing an int {e}"
            logger.error(msg)
            ret_val = httpCodes.HTTP_400_BAD_REQUEST
        else:
            if client_configuration is None:
                msg = "No client configuration model provided to save."
                logger.error(msg)
                ret_val = httpCodes.HTTP_400_BAD_REQUEST
            else:
                if replace:
                    sql_action = "REPLACE"
                    ret_val = httpCodes.HTTP_200_OK
                else:
                    sql_action = "INSERT"
                    ret_val = httpCodes.HTTP_201_CREATED
                try:
                    session_id = session_id
                except Exception as e:
                    # no session open!
                    msg = "No session is open / Not authorized"
                    logger.error(msg)
                    ret_val = 401 # not authorized
                else:
                    self.open_connection(caller_name=fname) # make sure connection is open
                    try:
                        with closing(self.db.cursor(buffered=True, dictionary=True)) as curs:
                            for item in client_configuration.configList:
                                configName = item.configName
                                configSettings = item.configSettings
                                
                                try:
                                    config_json = json.dumps(configSettings, indent=2)  # expand json in table! 2021-03-21

                                except Exception as e:
                                    logger.error(f"Error converting configuration to json {e}.")
                                    return ret_val
                    
                                sql = f"""{sql_action} INTO 
                                            api_client_configs(client_id,
                                                               config_name, 
                                                               config_settings, 
                                                               session_id
                                                              )
                                                              VALUES 
                                                               (%s, %s, %s, %s)"""
                                
                                succ = curs.execute(sql,
                                                    (client_id_int,
                                                     configName,
                                                     config_json, 
                                                     session_id
                                                    )
                                                   )
                                warnings = curs.fetchwarnings()
                                if warnings:
                                    for warning in warnings:
                                        logger.warning(warning)
                                
                            self.db.commit()
            
                    except Exception as e:
                        if sql_action == "REPLACE":
                            msg = f"Error updating (replacing) client config: {e}"
                            logger.error(msg)
                            ret_val = 400
                        else: # insert
                            msg = f"Error saving client config: {e}"
                            logger.error(msg)
                            ret_val = 409
            
                    self.close_connection(caller_name=fname) # make sure connection is closed
    
        return (ret_val, msg)

    def save_client_config_item(self, client_id:str, client_configuration_item: models.ClientConfigItem, session_id, replace=False, backup=True):
        """
        Save a client configuration item (config row).  Data format is up to the client.
        
        Returns True of False

        """
        fname = "save_client_config_item"
        msg = "OK"
        # convert client id to int
        try:
            client_id_int = int(client_id)
        except Exception as e:
            msg = f"ClientConfigError: Client ID should be a string containing an int {e}"
            logger.error(msg)
            ret_val = httpCodes.HTTP_400_BAD_REQUEST
        else:
            if client_configuration_item is None:
                msg = "ClientConfigError: No client configuration item model provided to save."
                logger.error(msg)
                ret_val = httpCodes.HTTP_400_BAD_REQUEST
            else:
                if replace:
                    sql_action = "REPLACE"
                    ret_val = httpCodes.HTTP_200_OK
                else:
                    sql_action = "INSERT"
                    ret_val = httpCodes.HTTP_201_CREATED
                try:
                    session_id = session_id
                except Exception as e:
                    # no session open!
                    msg = "ClientConfigError: No session is open / Not authorized"
                    logger.error(msg)
                    ret_val = 401 # not authorized
                else:
                    self.open_connection(caller_name=fname) # make sure connection is open
                    try:
                        with closing(self.db.cursor(buffered=True, dictionary=True)) as curs:
                            configName = client_configuration_item.configName
                            configSettings = client_configuration_item.configSettings
                            
                            try:
                                config_json = json.dumps(configSettings, indent=2)  # expand json in table! 2021-03-21
                            except Exception as e:
                                logger.error(f"ClientConfigError: Error converting configuration to json {e}.")
                                return ret_val
                
                            sql = f"""{sql_action} INTO 
                                        api_client_configs(client_id,
                                                           config_name, 
                                                           config_settings, 
                                                           session_id
                                                          )
                                                          VALUES 
                                                           (%s, %s, %s, %s)"""
                            if backup and sql_action == "REPLACE":
                                configNameBack = configName + "." + ".bak." + datetime.utcfromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')
                                logger.info(f"Saving Backup {configNameBack} of config before writing over it.")
                                succ = curs.execute(sql,
                                                    (client_id_int,
                                                     configNameBack,
                                                     config_json, 
                                                     session_id
                                                    )
                                                   )
                                warnings = curs.fetchwarnings()
                                if warnings:
                                    for warning in warnings:
                                        logger.warning(warning)

                            # now save
                            succ = curs.execute(sql,
                                                (client_id_int,
                                                 configName,
                                                 config_json, 
                                                 session_id
                                                )
                                               )

                            warnings = curs.fetchwarnings()
                            if warnings:
                                for warning in warnings:
                                    logger.warning(warning)
                            
                            self.db.commit()
            
                    except Exception as e:
                        if sql_action == "REPLACE":
                            msg = f"ClientConfigError: Error updating (replacing) client config: {e}"
                            logger.error(msg)
                            ret_val = 400
                        else: # insert
                            msg = f"ClientConfigError: Error saving client config: {e}"
                            logger.error(msg)
                            ret_val = 409
            
                    self.close_connection(caller_name=fname) # make sure connection is closed
    
        return (ret_val, msg)

    def get_client_config(self, client_id: str, client_config_name: str):
        """
        Get the requested standard client config name (template of sorts)
        
        Note: Session_id from client_configs is simply the session id for which the data
              was saved.  This will be admin, and is currently of no use, even though it
              is returned.
        
        >>> ocd = opasCentralDB()
        >>> model = models.ClientConfigList(configList=[models.ClientConfigItem(configName="demo", configSettings={"A":"123", "B":"1234"})])
        >>> ocd.save_client_config(client_id="123", client_configuration=model, session_id="test123", replace=True)
        (200, 'OK')
        >>> ocd.get_client_config("123", "test")
        ClientConfigList(configList=[ClientConfigItem(api_client_id=123, session_id='test123', configName='test', configSettings={'A': '123', 'B': '1234'})])
        >>> ocd.get_client_config("123", "test, test2")
        ClientConfigList(configList=[ClientConfigItem(api_client_id=123, session_id='test123', configName='test', configSettings={'A': '123', 'B': '1234'}), ClientConfigItem(api_client_id=123, session_id='test123', configName='test2', configSettings={'C': '456', 'D': '5678'})])
        >>> ocd.get_client_config("123", "doesntexist")
        
        Last case get used to return"
        ClientConfigList(configList=[])
        
        """
        fname = "get_client_config"
        ret_val = None
        if "," in client_config_name:
            client_config_name_list = [x.strip() for x in client_config_name.split(',')]
        else:
            client_config_name_list = [client_config_name.strip()]
            
        self.open_connection(caller_name=fname) # make sure connection is open
        try:
            client_id_int = int(client_id)
        except Exception as e:
            msg = f"Client ID should be a string containing an int {e}"
            logger.error(msg)
            ret_val = httpCodes.HTTP_400_BAD_REQUEST
        else:
            if self.db is not None:
                with closing(self.db.cursor(buffered=True, dictionary=True)) as curs:
                    ret_val_list = []
                    for client_config_name in client_config_name_list:
                        sql = f"""SELECT *
                                  FROM api_client_configs
                                  WHERE client_id = {client_id_int}
                                  AND config_name = '{client_config_name}'"""
            
                        try:
                            curs.execute(sql)
                            warnings = curs.fetchwarnings()
                            if warnings:
                                for warning in warnings:
                                    logger.warning(warning)
                            
                            if curs.rowcount >= 1:
                                clientConfig = curs.fetchone()
                                ret_val = models.ClientConfigs(**clientConfig)
                            else:
                                ret_val = None
    
                            try:
                                if ret_val is not None:
                                    ret_val_list.append(models.ClientConfigItem(configName = ret_val.config_name,
                                                                                configSettings=json.loads(ret_val.config_settings),
                                                                                api_client_id=ret_val.client_id, 
                                                                                session_id=ret_val.session_id
                                                                               )
                                                       )
                            except Exception as e:
                                ret_val = None
                                logger.error(f"Error converting config from database. Check json syntax in database {e}")
                                
                        except Exception as e:
                            ret_val = None
                            logger.error(f"Error getting config item from database {e}")
                            
                    if ret_val_list is not None:
                        try:
                            # convert to final return model, a list of ClientConfigItems
                            ret_val = models.ClientConfigList(configList = ret_val_list)
                            logger.debug("Config list returned.")
                        except Exception as e:
                            ret_val = None
                            logger.error(f"Error converting list of config items from database. Check json syntax in database {e}")
                    elif ret_val is not None:
                        logger.debug("Config item returned.")
                    else:
                        logger.error("No config returned.")
            else:
                logger.error(f"self.db connection is not set/missing. Can't get client config.")
                
                
            self.close_connection(caller_name=fname) # make sure connection is closed
    
        return ret_val

    def del_client_config(self, client_id: int, client_config_name: str):
        """
        
        >>> ocd = opasCentralDB()
        >>> ocd.del_client_config(2, "demo")
        
        """
        fname = "del_client_config"
        ret_val = None
        saved = self.get_client_config(client_id, client_config_name)
        if "," in client_config_name:
            client_config_name_list = [x.strip() for x in client_config_name.split(',')]
        else:
            client_config_name_list = [client_config_name.strip()]

        # open after fetching, since db is closed by call.
        self.open_connection(caller_name=fname) # make sure connection is open
        try:
            client_id_int = int(client_id)
        except Exception as e:
            msg = f"Client ID should be a string containing an int {e}"
            logger.error(msg)
            ret_val = httpCodes.HTTP_400_BAD_REQUEST
        else:
            if saved is not None:
                for client_config_name in client_config_name_list:
                    sql = f"""DELETE FROM api_client_configs
                              WHERE client_id = {client_id_int}
                              AND config_name = '{client_config_name}'"""
            
                    with closing(self.db.cursor(buffered=True, dictionary=True)) as curs:
                        curs.execute(sql)
                        row_count = curs.rowcount
                        if row_count >= 1:
                            ret_val = saved
                            self.db.commit()
                        else:
                            ret_val = None
                
            self.close_connection(caller_name=fname) # make sure connection is closed

        return ret_val

    def record_document_view(self, document_id, session_info=None, view_type="Abstract"):
        """
        Add a record to the api_doc_views table for specified view_type (Abstract, Document, PDF, PDFOriginal, or EPub)

        Tested in main instance docstring
        
        """
        fname = "record_document_view"
        ret_val = None
        self.open_connection(caller_name=fname) # make sure connection is open
        try:
            session_id = session_info.session_id
            user_id =  session_info.user_id
        except:
            # no session open!
            logger.debug("No session is open")
            return ret_val
        try:
            if view_type.lower() != "abstract" and view_type.lower() != "image/jpeg":
                if self.db is not None:
                    with closing(self.db.cursor()) as cursor:
                        try:
                            sql = """INSERT INTO 
                                        api_docviews(user_id, 
                                                      document_id, 
                                                      session_id, 
                                                      type, 
                                                      datetimechar
                                                     )
                                                     VALUES 
                                                      (%s, %s, %s, %s, %s)"""
                            
                            cursor.execute(sql,
                                           (user_id,
                                            document_id,
                                            session_id, 
                                            view_type, 
                                            datetime.utcfromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')
                                            )
                                           )
                            self.db.commit()
                            cursor.close()
                            ret_val = True
                
                        except Exception as e:
                            logger.error(f"Error saving document {document_id} view {view_type} for session {session_id} and user_id {user_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error checking document view type {view_type}: {e}")

        self.close_connection(caller_name=fname) # make sure connection is closed

        return ret_val
   
    def verify_admin(self, session_info):
        """
        Find if this is an admin, and return user info for them.
        Returns a user object
        """
        if session_info.admin:
            ret_val = True
        else:
            ret_val = False
            
        return ret_val   

    def delete_all_article_data(self):
        """
        We need this data, so don't test!
        Disabled:
        > ocd = opasCentralDB()
        > ocd.delete_all_article_data()
        """
        self.do_action_query(querytxt="DELETE FROM api_biblioxml", queryparams=None)
        self.do_action_query(querytxt="DELETE FROM api_articles", queryparams=None)
        
    #----------------------------------------------------------------------------------------
    def do_action_query(self, querytxt, queryparams, contextStr=None):
    
        fname = "do_action_query"
        ret_val = None
        localDisconnectNeeded = False
        if self.connected != True:
            self.open_connection(caller_name=fname) # make sure connection is open
            localDisconnectNeeded = True
            
        with closing(self.db.cursor(buffered=True, dictionary=True)) as dbc:
            try:
                ret_val = dbc.execute(querytxt, queryparams)
            except mysql.connector.DataError as e:
                logger.error(f"DBError: Art: {contextStr}. DB Data Error {e} ({querytxt})")
                ret_val = None
                # raise self.db.DataError(e)
            except mysql.connector.OperationalError as e:
                logger.error(f"DBError: Art: {contextStr}. DB Operation Error {e} ({querytxt})")
                raise mysql.connector.OperationalError(e)
            except mysql.connector.IntegrityError as e:
                logger.error(f"DBError: Art: {contextStr}. DB Integrity Error {e} ({querytxt})")
                raise mysql.connector.IntegrityError(e)
            except mysql.connector.InternalError as e:
                logger.error(f"DBError: Art: {contextStr}. DB Internal Error {e} ({querytxt})")
                raise mysql.connector.InternalError(e)
            except mysql.connector.ProgrammingError as e:
                logger.error(f"DBError: DB Programming Error {e} ({querytxt})")
                raise mysql.connector.ProgrammingError(e)
            except mysql.connector.NotSupportedError as e:
                logger.error(f"DBError: DB Feature Not Supported Error {e} ({querytxt})")
                raise mysql.connector.NotSupportedError(e)
            except Exception as e:
                logger.error(f"DBError: Exception: %s" % (e))
                raise Exception(e)
            else:
                self.db.commit()
        
        if localDisconnectNeeded == True:
            # if so, commit any changesand close.  Otherwise, it's up to caller.
            self.close_connection(caller_name=fname) # make sure connection is open
        
        return ret_val

    #----------------------------------------------------------------------------------------
    def do_action_query_silent(self, querytxt, queryparams, contextStr=None):
    
        fname = "do_action_query_silent"
        ret_val = None
        localDisconnectNeeded = False
        if self.connected != True:
            self.open_connection(caller_name=fname) # make sure connection is open
            localDisconnectNeeded = True
            
        with closing(self.db.cursor(buffered=True, dictionary=True)) as curs:
            try:
                ret_val = curs.execute(querytxt, queryparams)
            except Exception as e:
                raise Exception(e)
    
        if localDisconnectNeeded == True:
            # if so, commit any changesand close.  Otherwise, it's up to caller.
            self.db.commit()
            self.close_connection(caller_name=fname) # make sure connection is open
        
        return ret_val
    
    #----------------------------------------------------------------------------------------
    def log_pads_calls(self,
                       caller,
                       reason, 
                       session_id,
                       pads_call, # PaDS URL
                       ip_address=None, 
                       params=None,  # full url
                       api_endpoint_id=0, 
                       return_status_code=0,
                       status_message=None):
        """
        Track pads calls
        2021-11-08 Don't log to DB table temp_trackpads_calls anymore.  Just to debug output.
        """
        # Just output to STDOUT
        logger.debug (f"Track Calls to PaDS ({time.time()}): Session ID: {session_id}; ip address: {ip_address}. PaDS Call: {pads_call}")
    
        return 

#================================================================================================================================

if __name__ == "__main__":
    print (40*"*", "opasCentralDBLib Tests", 40*"*")
    print (f"Running in Python {sys.version_info[0]}.{sys.version_info[1]}")
   
    logger = logging.getLogger(__name__)
    # extra logging for standalong mode 
    # logger.setLevel(logging.DEBUG)
    # create console handler and set level to debug
    ch = logging.StreamHandler()
    # ch.setLevel(logging.DEBUG)
    # create formatter
    formatter = logging.Formatter('%(asctime)s %(name)s %(lineno)d - %(levelname)s %(message)s')    
    # add formatter to ch
    ch.setFormatter(formatter)
    # add ch to logger
    logger.addHandler(ch)
    
    ocd = opasCentralDB()
    # check this user permissions 
    #ocd.get_dict_of_products()
    #ocd.get_subscription_access("IJP", 421)
    #ocd.get_subscription_access("BIPPI", 421)
    #docstring tests
    import doctest
    doctest.testmod(optionflags=doctest.ELLIPSIS|doctest.NORMALIZE_WHITESPACE)
    #doctest.testmod()    
    print ("Fini. Tests complete.")