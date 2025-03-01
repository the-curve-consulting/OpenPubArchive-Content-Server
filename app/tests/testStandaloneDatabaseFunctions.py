#!/usr/bin/env python
# -*- coding: utf-8 -*-

import unittest
import unitTestConfig
from config import msgdb
import opasCentralDBLib

ocd = opasCentralDBLib.opasCentralDB()

class TestStandaloneDatabaseFunctions(unittest.TestCase):
    """
    Tests
    
    Note: tests are performed in alphabetical order, hence the function naming
          with forced order in the names.
    
    """

    def test_get_articles_newer_than(self):
        data = ocd.get_articles_newer_than(days_back=30)
        print (data)
        
    def test_get_articles_newer_than_2(self):
        data = ocd.get_articles_newer_than(days_back=10)
        print (data)
        
    def test_get_articles_newer_than_3(self):
        data = ocd.get_articles_newer_than(days_back=5)
        print (data)
        
    def test_get_user_message(self):
        data = msgdb.get_user_message(msg_code="300")
        print (data)
        data2 = msgdb.get_user_message(msg_code=300)
        assert (data == data2)
        

if __name__ == '__main__':
    unittest.main()
    print ("Tests Complete.")