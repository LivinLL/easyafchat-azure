import sqlite3

def view_all_records():
    conn = sqlite3.connect('easyafchat.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM companies')
    records = cursor.fetchall()
    
    for i, record in enumerate(records, 1):
        print('-' * 80)
        print(f'Record ID: {i}')
        print(f'Chatbot ID: {record[0]}')
        print(f'Company URL: {record[1]}')
        print(f'Pinecone Host URL: {record[2]}')
        print(f'Pinecone Index: {record[3]}')
        print(f'Pinecone Namespace: {record[4]}')
        print(f'Created At: {record[5]}')
        print(f'Updated At: {record[6]}')
        print(f'Home Text Length: {len(record[7])} characters')
        print(f'About Text Length: {len(record[8])} characters')
        print(f'Processed Content Length: {len(record[9])} characters\n')
    
    print(f'Total Records: {len(records)}')
    conn.close()

if __name__ == '__main__':
    view_all_records()
    