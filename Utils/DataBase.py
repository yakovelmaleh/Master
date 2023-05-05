import mysql.connector


DB_USER = 'root'
DB_PASSWORD = 'o9r1eN%^ZX'
DB_NAME = 'data_base_os'

def conncetToDB():
    mysql_con = mysql.connector.connect(user=DB_USER, password=DB_PASSWORD,
                                        host='localhost',
                                        auth_plugin='mysql_native_password', use_unicode=True)
    return mysql_con

def connectToSpecificDB(name):
    mysql_con = mysql.connector.connect(user=DB_USER, password=DB_PASSWORD,
                                        host='localhost', database=name,
                                        auth_plugin='mysql_native_password', use_unicode=True)

    mysql_con.cursor().execute(f'USE {name}')
    return mysql_con


