

# Setup a Solr instance. The timeout is optional.
# #TODO
# switched from pysolr to solrpy for authentication feature...but solrpy has a few bugs and doesn't
# seem to be updated anymore.  And pysolr is, and works, per usage in solrXMLWebLoad.py.  So perhaps
# this should be switched back.
# solr = pysolr.Solr('http://localhost:8983/solr/pepwebproto', timeout=10)
# This is the old way -- should switch to class Solr per https://pythonhosted.org/solrpy/reference.html
#
#from solrq import Q
import solrpy as solr
import pysolr
from localsecrets import SOLRUSER, SOLRPW, SOLRURL
import opasConfig

# These are the solr database names used
SOLR_DOCS = "pepwebdocs"
# SOLR_REFS = "pepwebrefs"
SOLR_AUTHORS = "pepwebauthors"
SOLR_GLOSSARY = "pepwebglossary"

SOLR_DEFAULT_CORE = SOLR_DOCS

# constants
COMMITLIMIT = 1000  # commit the load to Solr every X articles

# for pysolr! (solrpy is now limited to a variant of term search and used only in opasSolrPyLib.py)
if SOLRUSER is not None and SOLRPW is not None:
    solr_call = pysolr.Solr(SOLRURL, auth=(SOLRUSER, SOLRPW))
    solr_docs2 = pysolr.Solr(SOLRURL + SOLR_DOCS, auth=(SOLRUSER, SOLRPW))
    #solr_docs_term_search = pysolr.Solr(SOLRURL + SOLR_DOCS, "/terms", auth=(SOLRUSER, SOLRPW))
    solr_gloss2 = pysolr.Solr(SOLRURL + SOLR_GLOSSARY, auth=(SOLRUSER, SOLRPW))
    solr_authors2 = pysolr.Solr(SOLRURL + SOLR_AUTHORS, auth=(SOLRUSER, SOLRPW))
    #solr_authors_term_search2 = pysolr.Solr(solr_authors, "/terms", auth=(SOLRUSER, SOLRPW))
    solr_like_this2 = pysolr.Solr(solr_authors2, "/mlt", auth=(SOLRUSER, SOLRPW))
else: #  no user and password needed
    solr_call = pysolr.Solr(SOLRURL)
    solr_docs2 = pysolr.Solr(SOLRURL + SOLR_DOCS)
    #solr_docs_term_search = solr_docs2  # term_index = solr_docs2.suggest_terms(term_field, term_partial.lower())
    solr_gloss2 = pysolr.Solr(SOLRURL + SOLR_GLOSSARY)
    solr_authors2 = pysolr.Solr(SOLRURL + SOLR_AUTHORS)
    #solr_authors_term_search2 = pysolr.Solr(solr_authors2, "/terms")
    solr_like_this2 = pysolr.Solr(solr_authors2, "/mlt")

# define cores for ExtendedSearch
EXTENDED_CORES = {
    "pepwebdocs": solr_docs2,
    "pepwebgloss": solr_gloss2,
    "pepwebauthors": solr_authors2,
    # "pepwebauthors_terms": solr_authors_term_search,
}

EXTENDED_DOCS_DEFAULTS = {
    "fl" : opasConfig.DOCUMENT_ITEM_SUMMARY_FIELDS, 
}

EXTENDED_GLOSSARY_DEFAULTS = {
    "fl" : opasConfig.GLOSSARY_ITEM_DEFAULT_FIELDS,    
}

EXTENDED_AUTHOR_DEFAULTS = {
    "fl" : opasConfig.AUTHOR_ITEM_DEFAULT_FIELDS, 
}

EXTENDED_CORES_DEFAULTS = {
    "pepwebdocs": EXTENDED_DOCS_DEFAULTS,
    "pepwebgloss": EXTENDED_GLOSSARY_DEFAULTS,
    "pepwebauthors": EXTENDED_AUTHOR_DEFAULTS,
}

CORES = {
    "docs": solr_docs2,
    "gloss": solr_gloss2,
    "authors": solr_authors2,
    # "authors_terms": solr_authors_term_search,
}

if __name__ == "__main__":
    import sys
    sys.path.append('./config')

    import doctest
    doctest.testmod(optionflags=doctest.ELLIPSIS|doctest.NORMALIZE_WHITESPACE)
    print ("All tests complete!")
    print ("Fini")
