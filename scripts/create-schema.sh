#!/bin/bash
set -e
cd "$(dirname "$0")"

mysql -h 127.0.0.1 -u root -pMySQLRootPassword --ssl-mode=DISABLED pep < ../sql/schemas/opascentralStructure.sql
echo "Schema imported successfully!"