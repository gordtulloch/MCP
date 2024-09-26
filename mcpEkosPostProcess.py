############################################################################################################
#
# Name        : postProcess.py
# Purpose     : Script to call after an image is taken to give it a standard name, add it to an index 
#               database, and move it to a repository
# Author      : Gord Tulloch
# Date        : January 25 2024
# License     : GPL v3
# Dependencies: Imagemagick and SIRIL needs to be install for live stacking
#               Tested with EKOS, don't know if it'll work with other imaging tools 
# Usage       : This script could be run after an image (single image) or after a sequence if live stacking  
#               is also being run
# TODO:
#      - Calibrate image prior to storing and stacking it (master dark/flat/bias)
#
############################################################################################################ 
import os
from astropy.io import fits
import sqlite3
import shutil
import uuid
from pathlib import Path
from datetime import datetime
from mcpConfig import McpConfig

DEBUG=True

# Set up logging
import logging
logger = logging.getLogger("tMCP.log")

class EkosPostProcess(object):
    def __init__(self):
        self.config=McpConfig()
        self.port = self.config.get("REPOLOCATION")
        self.sourceFolder=self.config.get("EKOSIMAGEFOLDER")
        self.repoFolder=self.config.get("REPOFOLDER")
        self.dbName = self.repoFolder+"obsy.db"
        self.con = sqlite3.connect(self.dbName)
        self.cur = self.con.cursor()
        self.createDBTables()

    # Function definitions
    def submitFileToDB(fileName, hdr):
        if "DATE-OBS" in hdr:
            uuidStr=uuid.uuid4()
            sqlStmt="INSERT INTO fitsFile (unid, date, filename) VALUES ('{0}','{1}','{2}')".format(uuidStr,hdr["DATE-OBS"],fileName)

            try:
                cur.execute(sqlStmt)
                con.commit()
            except sqlite3.Error as er:
                logging.error('SQLite error: %s' % (' '.join(er.args)))
                logging.error("Exception class is: ", er.__class__)
                logging.error('SQLite traceback: ')
                exc_type, exc_value, exc_tb = sys.exc_info()
                logging.error(traceback.format_exception(exc_type, exc_value, exc_tb))
            
            for card in hdr:
                if type(hdr[card]) not in [bool,int,float]:
                    keywordValue=str(hdr[card]).replace('\'',' ')
                else:
                    keywordValue = hdr[card]
                sqlStmt="INSERT INTO fitsHeader (thisUNID, parentUNID, keyword, value) VALUES ('{0}','{1}','{2}','{3}')".format(uuid.uuid4(),uuidStr,card,keywordValue)

                try:
                    cur.execute(sqlStmt)
                    con.commit()
                except sqlite3.Error as er:
                    logging.error('SQLite error: %s' % (' '.join(er.args)))
                    logging.error("Exception class is: ", er.__class__)
                    logging.error('SQLite traceback: ')
                    exc_type, exc_value, exc_tb = sys.exc_info()
                    logging.error(traceback.format_exception(exc_type, exc_value, exc_tb))
        else:
            logging.error("Error: File not added to repo due to missing date is "+fileName)
            return False
        return True

    def createDBTables():
        if DEBUG:
            cur.execute("DROP TABLE if exists fitsFile")
            cur.execute("DROP TABLE if exists fitsHeader")
        cur.execute("CREATE TABLE if not exists fitsFile(unid, date, filename)")
        cur.execute("CREATE TABLE if not exists fitsHeader(thisUNID, parentUNID, keyword, value)")
        return

    def processImageToFile():
        # Scan the pictures folder
        for root, dirs, files in os.walk(os.path.abspath(sourceFolder)):
            for file in files:
                file_name, file_extension = os.path.splitext(os.path.join(root, file))

                # Ignore everything not a *fit* file
                if (file_extension !=".fits") or (file_extension !=".fit"):
                    continue
                if (file_extension ==".db"):
                    continue
                try:
                    hdul = fits.open(os.path.join(root, file))
                except ValueError as e:
                    logging.warning("Invalid FITS file. File not processed is "+str(os.path.join(root, file)))
                    continue   
        
                hdr = hdul[0].header
                if "FRAME" in hdr:
                    print(os.path.join(root, file))

                    # Create an os-friendly date
                    try:
                        datestr=hdr["DATE-OBS"].replace("T", " ")
                        datestr=datestr[0:datestr.find('.')]
                        dateobj=datetime.strptime(datestr, '%Y-%m-%d %H:%M:%S')
                        fitsDate=dateobj.strftime("%Y%m%d%H%M%S")
                    except ValueError as e:
                        logging.warning("Invalid date format in header. File not processed is "+str(os.path.join(root, file)))
                        continue

                    # Create a new standard name for the file based on what it is
                    if (hdr["FRAME"]=="Light"):
                        if ("OBJECT" in hdr):
                            newName=newName="{0}-{1}-{2}-{3}s-{4}x{5}-t{6}.fits".format(hdr["OBJECT"].replace(" ", ""),hdr["FILTER"],fitsDate,hdr["EXPTIME"],hdr["XBINNING"],hdr["YBINNING"],hdr["CCD-TEMP"])
                        else:
                            logging.warning("Invalid object name in header. File not processed is "+str(os.path.join(root, file)))
                            continue
                    elif hdr["FRAME"]=="Dark" or hdr["FRAME"]=="Flat" or hdr["FRAME"]=="Bias":
                        newName="{0}-{1}-{2}s-{3}x{4}-t{5}.fits".format(hdr["FRAME"],fitsDate,hdr["EXPTIME"],hdr["XBINNING"],hdr["YBINNING"],hdr["CCD-TEMP"])
                    else:
                        logging.warning("File not processed as FRAME not recognized: "+str(os.path.join(root, file)))
                    hdul.close()

                    # Create the folder structure (if needed)
                    fitsDate=dateobj.strftime("%Y%m%d")
                    if (hdr["FRAME"]=="Light"):
                        newPath=repoFolder+"Light/{0}/{1}/".format(hdr["OBJECT"].replace(" ", ""),fitsDate)
                    elif hdr["FRAME"]=="Dark":
                        newPath=repoFolder+"Calibrate/{0}/{1}/{2}/".format(hdr["FRAME"],hdr["EXPTIME"],fitsDate)
                    elif hdr["FRAME"]=="Flat":
                        newPath=repoFolder+"Calibrate/{0}/{1}/{2}/".format(hdr["FRAME"],hdr["FILTER"],fitsDate)
                    elif hdr["FRAME"]=="Bias":
                        newPath=repoFolder+"Calibrate/{0}/{1}/".format(hdr["FRAME"],fitsDate)

                    if not os.path.isdir(newPath):
                        os.makedirs (newPath)

                    # If we can add the file to the database move it to the repo
                    if (submitFile(newPath+newName.replace(" ", ""),hdr)):
                        if DEBUG:
                            moveInfo="Moving {0} to {1}\n".format(os.path.join(root, file),newPath+newName)
                            print(moveInfo)
                        shutil.move(os.path.join(root, file),newPath+newName)
                    else:
                        logging.warning("Warning: File not added to repo is "+str(os.path.join(root, file)))
                else:
                    logging.warning("File not added to repo - no FRAME card - "+str(os.path.join(root, file)))
    
    def processImageToS3(self):
        # Scan the pictures folder
        for root, dirs, files in os.walk(os.path.abspath(sourceFolder)):
            for file in files:
                file_name, file_extension = os.path.splitext(os.path.join(root, file))

                # Ignore everything not a *fit* file
                if (file_extension !=".fits") or (file_extension !=".fit"):
                    continue
                if (file_extension ==".db"):
                    continue
                try:
                    hdul = fits.open(os.path.join(root, file))
                except ValueError as e:
                    logging.warning("Invalid FITS file. File not processed is "+str(os.path.join(root, file)))
                    continue   
        
                hdr = hdul[0].header
                if "FRAME" in hdr:
                    print(os.path.join(root, file))

                    # Create an os-friendly date
                    try:
                        datestr=hdr["DATE-OBS"].replace("T", " ")
                        datestr=datestr[0:datestr.find('.')]
                        dateobj=datetime.strptime(datestr, '%Y-%m-%d %H:%M:%S')
                        fitsDate=dateobj.strftime("%Y%m%d%H%M%S")
                    except ValueError as e:
                        logging.warning("Invalid date format in header. File not processed is "+str(os.path.join(root, file)))
                        continue

                    # Create a new standard name for the file based on what it is
                    if (hdr["FRAME"]=="Light"):
                        if ("OBJECT" in hdr):
                            newName=newName="{0}-{1}-{2}-{3}s-{4}x{5}-t{6}.fits".format(hdr["OBJECT"].replace(" ", ""),hdr["FILTER"],fitsDate,hdr["EXPTIME"],hdr["XBINNING"],hdr["YBINNING"],hdr["CCD-TEMP"])
                        else:
                            logging.warning("Invalid object name in header. File not processed is "+str(os.path.join(root, file)))
                            continue
                    elif hdr["FRAME"]=="Dark" or hdr["FRAME"]=="Flat" or hdr["FRAME"]=="Bias":
                        newName="{0}-{1}-{2}s-{3}x{4}-t{5}.fits".format(hdr["FRAME"],fitsDate,hdr["EXPTIME"],hdr["XBINNING"],hdr["YBINNING"],hdr["CCD-TEMP"])
                    else:
                        logging.warning("File not processed as FRAME not recognized: "+str(os.path.join(root, file)))
                    hdul.close()

                    # Create the folder structure (if needed)
                    fitsDate=dateobj.strftime("%Y%m%d")
                    if (hdr["FRAME"]=="Light"):
                        newPath=repoFolder+"Light/{0}/{1}/".format(hdr["OBJECT"].replace(" ", ""),fitsDate)
                    elif hdr["FRAME"]=="Dark":
                        newPath=repoFolder+"Calibrate/{0}/{1}/{2}/".format(hdr["FRAME"],hdr["EXPTIME"],fitsDate)
                    elif hdr["FRAME"]=="Flat":
                        newPath=repoFolder+"Calibrate/{0}/{1}/{2}/".format(hdr["FRAME"],hdr["FILTER"],fitsDate)
                    elif hdr["FRAME"]=="Bias":
                        newPath=repoFolder+"Calibrate/{0}/{1}/".format(hdr["FRAME"],fitsDate)

                    if not os.path.isdir(newPath):
                        os.makedirs (newPath)

                    # If we can add the file to the database move it to the repo
                    if (submitFile(newPath+newName.replace(" ", ""),hdr)):
                        if DEBUG:
                            moveInfo="Moving {0} to {1}\n".format(os.path.join(root, file),newPath+newName)
                            print(moveInfo)
                        shutil.move(os.path.join(root, file),newPath+newName)
                    else:
                        logging.warning("Warning: File not added to repo is "+str(os.path.join(root, file)))
                else:
                    logging.warning("File not added to repo - no FRAME card - "+str(os.path.join(root, file)))
                    
if __name__ == "__main__":
    ekosPostProcess=EkosPostProcess()
    ekosPostProcess.processImageToFile()
    ekosPostProcess.con.close()
    logging.info("Finished processing images")
    exit(0)