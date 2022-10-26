SENDER_EMAIL = ''
TO_EMAIL = ''
SKEY = ''
EMAILPW = ''

from flask import Flask, request, render_template, send_file, redirect, url_for, make_response, session
from apscheduler.schedulers.background import BackgroundScheduler
from email.mime.application import MIMEApplication
from apscheduler.triggers.cron import CronTrigger
from email.mime.multipart import MIMEMultipart
from datetime import datetime as dt, timedelta
from email.mime.text import MIMEText
from random import randrange
from ast import literal_eval
from sqlite3 import connect
from pandas import read_sql
from shutil import rmtree
from smtplib import SMTP
from shutil import copy
from fpdf import FPDF
from os import mkdir
import atexit


# --- CONFIG / VARIABLES ---


app = Flask(__name__)
app.config['SECRET_KEY'] = SKEY
pdf_path = 'static/pdf_temp/'
excel_path = 'static/xlsx_temp/'
num_pdf_questions = 12
sql_insert_format = '''
INSERT INTO quiz_data (Name, Date, Score, [Time (Minutes)], [Number Range], Subtraction, [Split Font])
VALUES ('{0}', {1}, {2}, {3}, '{4}', '{5}', '{6}');
'''


# --- PAGES ---


# If user doesn't specify page, redirect them to login or home
@app.route('/')
def no_dir():
    if request.cookies.get('username'):
        return redirect(url_for('student_home'))
    else:
        return redirect(url_for('student_login'))

# Student login page
@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        if not request.cookies.get('username'):
            user_name = request.form.get('user_name')
            if user_name != '':
                # When they press submit, create a bunch of cookies that hold all their info
                response = make_response(redirect(url_for('student_home')))
                response.set_cookie('username', user_name, max_age=timedelta(days=365))
                response.set_cookie('numrange', '1', max_age=timedelta(days=365))
                response.set_cookie('subtraction', '0', max_age=timedelta(days=365))
                response.set_cookie('split', '0', max_age=timedelta(days=365))
                response.set_cookie('yellowbg', '0', max_age=timedelta(days=365))
                return response

    if not request.cookies.get('username'): return render_template('studentlogin.html')
    else: return redirect(url_for('student_home'))

# Student home page
@app.route('/student/home', methods=['GET', 'POST'])
def student_home():
    if request.cookies.get('username'):
        if request.method == 'POST':
            # Take a math quiz
            if request.form['submit_button'] == 'Start Math':
                return redirect(url_for('student_math'))
            
            # "Lougout" (Delete all cookies and redirect to login)
            elif request.form['submit_button'] == 'Logout':
                response = make_response(redirect(url_for('student_login')))
                response.set_cookie('username', '', expires=0)
                response.set_cookie('numrange', '', expires=0)
                response.set_cookie('subtraction', '', expires=0)
                response.set_cookie('split', '', expires=0)
                response.set_cookie('yellowbg', '', expires=0)
                return response

            # Save cookie options
            elif request.form['submit_button'] == 'Save Options':
                subtraction_cookie = '1' if request.form.get('subtractioncheckbox') else '0'
                font_cookie = '1' if request.form.get('fontcheckbox') else '0'
                bg_cookie = '1' if request.form.get('bgcheckbox') else '0'

                response = make_response(redirect(url_for('student_home')))
                response.set_cookie('numrange', request.form['numrange'], max_age=timedelta(days=365))
                response.set_cookie('subtraction', subtraction_cookie, max_age=timedelta(days=365))
                response.set_cookie('split', font_cookie, max_age=timedelta(days=365))
                response.set_cookie('yellowbg', bg_cookie, max_age=timedelta(days=365))
                return response

        return render_template('studenthome.html', username=request.cookies.get('username'), numrange=request.cookies.get('numrange'), subtraction=request.cookies.get('subtraction'), split=request.cookies.get('split'), bg=request.cookies.get('yellowbg'))
    else: return redirect(url_for('student_login'))

# Student math page
@app.route('/student/math')
def student_math():
    return render_template('studentmath.html', username=request.cookies.get('username'), numrange=request.cookies.get('numrange'), subtraction=request.cookies.get('subtraction'), split=request.cookies.get('split'), bg=request.cookies.get('yellowbg'))

# Get data from math quiz and write it do db 
@app.route('/student/math/postdata', methods=['POST'])
def get_math_data():
    data = literal_eval(request.data.decode('utf-8'))
    connection = connect('static/data.db')
    cursor = connection.cursor()

    if data['number_range'] == '1': number_range = '0 - 5'
    elif data['number_range'] == '2': number_range = '0 - 10'
    elif data['number_range'] == '3': number_range = '10 - 99'
    elif data['number_range'] == '4': number_range = '100 - 999'

    command = sql_insert_format.format(
        data['username'],
        data['date'],
        data['score'],
        round(int(data['time']) / 60, 2),
        number_range,
        'Yes' if data['subtraction'] == '1' else 'No',
        'Yes' if data['split_font'] == '1' else 'No',
    )

    cursor.execute(command)
    connection.commit()
    connection.close()

    return '1'

# Teacher login page 
@app.route('/teacher/login', methods=['POST', 'GET'])
def teacher_login():
    if request.method == 'POST':
        if request.form.get('password') == '1111':
            session['teacherlogin'] = 'True'
            return redirect(url_for(('teacher_home')))

    if session.get('teacherlogin') == 'True': return redirect(url_for('teacher_home'))
    else: return render_template('teacherlogin.html')

# Teacher home page
@app.route('/teacher/home', methods=['POST', 'GET'])
def teacher_home():
    if request.method == 'POST':
        if request.form.get('submit_button') == 'Worksheet Generator': return redirect(url_for('get_pdf'))
        elif request.form.get('submit_button') == 'Report Generator': return redirect(url_for('generate_report'))

    if session.get('teacherlogin') == 'True': return render_template('teacherhome.html')
    else: return redirect(url_for('teacher_login'))

# Report generator page
@app.route('/teacher/report', methods=['POST', 'GET'])
def generate_report():
    if request.method == 'POST' and session.get('teacherlogin') == 'True':
        # Get data from page
        username = "'" + request.form.get('name_input') + "'"
        date_start = request.form.get('start_date').replace('-', '')
        date_end = request.form.get('end_date').replace('-', '')
        date = dt.now()

        if not date_start or not date_end: return(redirect(url_for('generate_report')))

        # Generate Excel
        if request.form.get('excelcheckbox'):
            # Delete and remake directory where report is stored
            rmtree(excel_path)
            mkdir(excel_path)

            if username == "''": username = 'Name'
            dataframe = read_sql(f"SELECT * FROM quiz_data WHERE (Date >= {int(date_start)} AND Date <= {int(date_end)} AND Name = {username})", connect('static/data.db'))

            if username == 'Name': username = 'all'
            file_name = f'''math-spreadsheet-{username.replace(" ", "").replace("'", '').lower()}_{date.strftime("%Y-%m-%d")}.xlsx'''
            dataframe.to_excel(excel_path + file_name)
            return send_file(excel_path + file_name)

        # Generate PDF
        else:
            rmtree(pdf_path)
            mkdir(pdf_path)

            if username == "''": username = 'Name'
            names = sorted(list(set([name for name in read_sql(f"SELECT Name FROM quiz_data WHERE (Date >= {int(date_start)} AND Date <= {int(date_end)} AND Name = {username})", connect('static/data.db'))['Name']]))) # Get all names
            if username == "Name": username = 'all'
            file_name = f'''math-report-{username.replace(" ", "").replace("'", '').lower()}_{date.strftime("%Y-%m-%d")}.pdf'''

            pdf = FPDF('P', 'mm', 'Letter')
            pdf.add_page()
            pdf.set_font('Helvetica', size=15)

            for name in names:
                dataframe = read_sql(f"SELECT * FROM quiz_data WHERE (Date >= {int(date_start)} AND Date <= {int(date_end)} AND Name = '{name}')", connect('static/data.db')) # Get data from name

                # Create document header
                pdf.cell(102, 5, 'Math Report')
                date_start_rearrange = str(date_start)[4:6] + '/' + str(date_start)[6:8] + '/' + str(date_start)[:4][2:4]
                date_end_rearrange = str(date_end)[4:6] + '/' + str(date_end)[6:8] + '/' + str(date_end)[:4][2:4]
                pdf.cell(10, 5, f'Reporting Period: ({date_start_rearrange} - {date_end_rearrange})', ln=True)
                pdf.cell(10, 5, '__________________________________________________________________')
                pdf.ln(15)

                pdf.set_font(style='B')
                pdf.cell(10, 5, f'Student: {name}')
                pdf.set_font(style='')
                pdf.ln(15)

                # Set up data for table
                line_height = pdf.font_size * 1.5
                col_width = pdf.epw / 3.5

                student_data = [
                    [' ', 'Date', 'Time (Min)', 'Accuracy'],
                ]

                dates = [(str(int(str(date)[4:6])) + '/' + str(int(str(date)[6:8])) + '/' + str(date)[:4][2:4]) for date in dataframe['Date']]
                times = [str(time) for time in dataframe['Time (Minutes)']]
                scores = [str(score * 10) + '%' for score in dataframe['Score']]

                subtractions = [subtraction for subtraction in dataframe['Subtraction']]
                ranges = [range for range in dataframe['Number Range']]

                types = [f'Subtraction {ranges[i]}' if subtractions[i] == 'Yes' else f'Addition {ranges[i]}' for i in range(len(dataframe))]

                for i in range(len(dataframe)):
                    student_data.append([types[i], dates[i], times[i], scores[i]])

                # Create table
                previous_type = ''
                for row in student_data:
                    for data in row:
                        if '-' in data:
                            if data == previous_type: data = ' '
                            else: previous_type = data

                        pdf.multi_cell(col_width, line_height, data, border=0, ln=3, max_line_height=pdf.font_size)
                    pdf.ln(line_height)

                if name != names[len(names) - 1]: pdf.set_y(-1) # Crate new page

            pdf.output(pdf_path + file_name)
            return send_file(pdf_path + file_name)

    if session.get('teacherlogin') == 'True': return render_template('generatereport.html')
    else: return redirect(url_for('teacher_login'))

# PDF creation page
@app.route('/teacher/pdf', methods=['GET', 'POST'])
def get_pdf():
    if request.method == 'POST' and session.get('teacherlogin') == 'True':
        # Delete and remake PDF directory
        rmtree(pdf_path)
        mkdir(pdf_path)

        # Generate number values for questions
        random_num_list = []
        double_num_questions = num_pdf_questions * 2
        if request.form['submit_button'] == 'Numbers 0 - 5':
            random_num_list = [randrange(0, 6) for _ in range(double_num_questions)]
            num_underline = 2
        elif request.form['submit_button'] == 'Numbers 0 - 9':
            random_num_list = [randrange(0, 10) for _ in range(double_num_questions)]
            num_underline = 2
        elif request.form['submit_button'] == 'Numbers 10 - 99': 
            random_num_list = [randrange(10, 100) for _ in range(double_num_questions)]
            num_underline = 3
        elif request.form['submit_button'] == 'Numbers 100 - 999':
            random_num_list = [randrange(100, 1000) for _ in range(double_num_questions)]
            num_underline = 4

        file_name = f'math-questions_{dt.now().strftime("%Y-%m-%d_%H-%M-%S")}.pdf' # Create file name using current date and time
        operation = '-' if request.form.get('subtractioncheckbox') else '+'

        # Generate PDF differently depending on whether or not the split fonts switch is activated
        if request.form.get('splitcheckbox'): generate_pdf_split(random_num_list, file_name, num_underline, operation)
        else: generate_pdf_normal(random_num_list, file_name, num_underline, operation)

        return send_file(pdf_path + file_name) # Download PDF

    if session.get('teacherlogin') == 'True': return render_template('pdfcreator.html')
    else: return redirect(url_for('teacher_login'))


# --- PDF CREATION ---


# Generate PDF with problems (one font)
def generate_pdf_normal(random_num_list, file_name, num_underline, operation):
    if operation == '-': random_num_list = rearange_subtraction(random_num_list) # Rearange subtraction problems

    # Split random numbers into top and bottom operand list
    random_top_nums = random_num_list[:len(random_num_list) // 2]
    random_bottom_nums = random_num_list[len(random_num_list) // 2:]

    # Create pdf
    pdf = FPDF('P', 'mm', 'Letter')
    pdf.add_page()
    pdf.add_font('KG Teacher Helpers', '', 'static/KGTeacherHelpersMono.ttf', uni=True)
    quarter_num_questions = num_pdf_questions // 4
    for i in range(num_pdf_questions // 3):
        pdf.set_font('KG Teacher Helpers', '', 50)

        # Create first row (first number)
        pdf.cell(40, 20, ' ' * 18 + f'{random_top_nums[i * quarter_num_questions + 0]}')
        pdf.cell(40, 20, ' ' * 42 + f'{random_top_nums[i * quarter_num_questions + 1]}')
        pdf.cell(40, 20, ' ' * 66 + f'{random_top_nums[i * quarter_num_questions + 2]}', ln=True)

        pdf.cell(0, 5, '', ln=True) # Spacer

        # Create second row (second number)
        pdf.cell(40, 0, ' ' * 11 + f'{operation} {random_bottom_nums[i * quarter_num_questions + 0]}')
        pdf.cell(40, 0, ' ' * 35 + f'{operation} {random_bottom_nums[i * quarter_num_questions + 1]}')
        pdf.cell(40, 0, ' ' * 59 + f'{operation} {random_bottom_nums[i * quarter_num_questions + 2]}', ln=True)

        # Create third row (underline)
        pdf.set_font('Helvetica', '', 50)
        pdf.cell(40, 0, ' ' * 2 + '_' * num_underline)
        pdf.cell(40, 0, ' ' * 7 + '_' * num_underline)
        pdf.cell(40, 0, ' ' * 12 + '_' * num_underline, ln=True)

        pdf.cell(0, 37, '', ln=True) # Spacer

    pdf.output(pdf_path + file_name)

# Generate PDF with problems (two fonts)
def generate_pdf_split(random_num_list, file_name, num_underline, operation):
    if operation == '-': random_num_list = rearange_subtraction(random_num_list) # Rearange subtraction problems

    # Split random numbers into top and bottom operand list
    random_top_nums = random_num_list[:len(random_num_list) // 2]
    random_bottom_nums = random_num_list[len(random_num_list) // 2:]

    # Split numbers into their digits for comparison
    random_top_digits = [[int(digit) for digit in str(integer)] for integer in random_top_nums]
    random_bottom_digits = [[int(digit) for digit in str(integer)] for integer in random_bottom_nums]


    # Create pdf
    pdf = FPDF('P', 'mm', 'Letter')
    pdf.add_page()
    pdf.add_font('KG Teacher Helpers', '', 'static/KGTeacherHelpersMono.ttf', uni=True)
    pdf.add_font('KG Teacher Helpers Dotless', '', 'static/KGTeacherHelpersMonoNodot.ttf', uni=True)
    quarter_num_questions = num_pdf_questions // 4
    for i in range(num_pdf_questions // 3):
        # This is the worst code I have ever written
        # Please avert your gaze

        num_digits = len(random_top_digits[0])

        # Create first row (first number)
        for k in range(3):
            if k == 1 or k == 2: pdf.cell(28, 20, ' ' * 15)
            if num_digits == 2 and k != 0: pdf.cell(8, 20, ' ' * 15)
            elif num_digits == 1 and k != 0: pdf.cell(17, 20, ' ' * 15)
            for j in range(num_digits):
                if random_top_digits[i * quarter_num_questions + k][j] >= random_bottom_digits[i * quarter_num_questions + k][j]: pdf.set_font('KG Teacher Helpers Dotless', '', 50)
                else: pdf.set_font('KG Teacher Helpers', '', 50)
                pdf.cell(9, 20, ' ' * 18 + f'{random_top_digits[i * quarter_num_questions + k][j]}')
            pdf.cell(10, 20, ' ' * 20)

        pdf.cell(0, 15, '', ln=True) # Spacer

        # Create second row (second number)
        for k in range(3):
            if k == 1 or k == 2: pdf.cell(16, 20, ' ' * 15)
            if num_digits == 2 and k != 0: pdf.cell(8, 20, ' ' * 15)
            elif num_digits == 1 and k != 0: pdf.cell(17, 20, ' ' * 15)
            pdf.cell(12, 20, ' ' * 11 + f'{operation}')
            for j in range(num_digits):
                if random_bottom_digits[i * quarter_num_questions + k][j] > random_top_digits[i * quarter_num_questions + k][j]: pdf.set_font('KG Teacher Helpers Dotless', '', 50)
                else: pdf.set_font('KG Teacher Helpers', '', 50)
                pdf.cell(9, 20, ' ' * 7 + f'{random_bottom_digits[i * quarter_num_questions + k][j]}')
            pdf.cell(10, 20, ' ' * 20)

        pdf.cell(0, 10, '', ln=True) # Spacer

        # Create third row (underline)
        pdf.set_font('Helvetica', '', 50)
        pdf.cell(40, 0, ' ' * 2 + '_' * num_underline)
        pdf.cell(40, 0, ' ' * 7 + '_' * num_underline)
        pdf.cell(40, 0, ' ' * 12 + '_' * num_underline, ln=True)

        pdf.cell(0, 37, '', ln=True) # Spacer

    pdf.output(pdf_path + file_name)

# Rearange a list of numbers for subtraction so negative numbers are impossible
def rearange_subtraction(num_list):
    new_num_list = [0] * (num_pdf_questions * 2)
    for i in range(num_pdf_questions):
        if num_list[i] > num_list[i + 12]:
            new_num_list[i] = num_list[i]
            new_num_list[i + 12] = num_list[i + 12]
        else:
            new_num_list[i] = num_list[i + 12]
            new_num_list[i + 12] = num_list[i]

    return new_num_list


# --- WEEKLY SPREADSHEET EMAIL ---


# Send email with excel sheet every week
def email_data():
    # Delete and remake directory where spreadsheet is stored
    rmtree(excel_path)
    mkdir(excel_path)

    # Get data from database and write it to Excel spreadsheet
    last_week = dt.now() - timedelta(days=7)
    last_week_int = int(last_week.strftime('%Y%m%d'))
    dataframe = read_sql(f"SELECT * FROM quiz_data WHERE Date > {last_week_int}", connect('static/data.db'))
    file_name = f'math-spreadsheet_{dt.now().strftime("%Y-%m-%d")}.xlsx'
    dataframe.to_excel(excel_path + file_name)

    # This file attachment bit is from here:
    # https://stackoverflow.com/questions/3362600/how-to-send-email-attachments
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = TO_EMAIL
    msg['Subject'] = f'Math spreadsheet for the week of {last_week.strftime("%d %b %Y")}'

    with open(excel_path + file_name, "rb") as file:
        spreadsheet = MIMEApplication(file.read(), Name=file_name)
    spreadsheet['Content-Disposition'] = 'attachment; filename="%s"' % file_name
    msg.attach(spreadsheet)

    # Start SMTP server and send email
    smtp = SMTP('smtp.gmail.com', 587)
    smtp.ehlo()
    smtp.starttls()
    smtp.login(SENDER_EMAIL, EMAILPW)
    smtp.sendmail(SENDER_EMAIL, TO_EMAIL, msg.as_string())
    smtp.close()

    copy('static/data.db', 'static/data_backup.db') # Copy database locally (In case I included a bug that messes up the database)

# Email warning before database deletion
def email_warning():
    next_week = (dt.now() + timedelta(days=7)).strftime('%D')

    # This file attachment bit is from here:
    # https://stackoverflow.com/questions/3362600/how-to-send-email-attachments
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = TO_EMAIL
    msg['Subject'] = 'WARNING: DATABASE DELETION'
    msg.attach(MIMEText(f'The database containing the data from student math tests will be cleared one week from now on {next_week}.\nPlease generate any reports you may need before that time!'))

    # Start SMTP server and send email
    smtp = SMTP('smtp.gmail.com', 587)
    smtp.ehlo()
    smtp.starttls()
    smtp.login(SENDER_EMAIL, EMAILPW)
    smtp.sendmail(SENDER_EMAIL, TO_EMAIL, msg.as_string())
    smtp.close()

# Delete contents of database
def delete_db():
    connection = connect('static/data.db')
    cursor = connection.cursor()
    cursor.execute('DELETE FROM quiz_data;')
    connection.commit()
    connection.close()



if __name__=='__main__':
    scheduler = BackgroundScheduler()
    scheduler.start()

    # Email report once a week / backup db
    weekly_email_trigger = CronTrigger(day_of_week="4", hour="9", minute="0", second="0")
    scheduler.add_job(func=email_data, trigger=weekly_email_trigger)

    # Email warning 7 days before database deletion
    yearly_warning_trigger = CronTrigger(month='7', day='1', hour='15', minute='0', second='0')
    scheduler.add_job(func=email_warning, trigger=yearly_warning_trigger)

    # Delete from database once per year
    yearly_deletion_trigger = CronTrigger(month='7', day='8', hour='15', minute='0', second='0')
    scheduler.add_job(func=delete_db, trigger=yearly_deletion_trigger)

    atexit.register(lambda: scheduler.shutdown())

    app.run(debug=False, port=5555, host='0.0.0.0') # Run website on port 5555 on current machine
