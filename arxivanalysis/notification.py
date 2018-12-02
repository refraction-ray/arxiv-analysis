"""
module for send html email of summary of highlight on arxiv
"""

import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr


def makecss():
    return ('<style> .id {font-size: large; color: #b30000 !important; background: #F0EEE4; border:#999999 solid 1px !important;padding: 2px !important;}'
                '.title {font-size: large; font-weight: bold; line-height: 120%%; }'
                '.summary {line-height: 130%%; }'
                '.authors {font-style:italic; }'
                '</style>')

def makehtml(content,count):
    htmltext = (
                '<p class="id">[%s] &nbsp  arXiv:<a href="%s">%s</a> &nbsp  &nbsp Keywords: %s</p>'
                '<p class="title">%s</p>'
                '<p class="authors">%s </p>'
                '<hr>'
                '<p class="summary">%s</p>'
               )%(count, content['arxiv_url'], content['arxiv_id'],", ".join([w[0] for w in content['keyword']]),
                                 content['title'],", ".join(content['authors']), content['summary'])
    return htmltext

def makemailcontent(headline, contents):
    body = makecss() + " ".join([makehtml(it, i + 1) for i, it in enumerate(contents)])
    return ('<html><body>'
            '<p class="title">%s</p>'
            '%s'
            '</body></html>'
            )%(headline, body)

def sendmail(sender, sender_alias, password, server, port, user, user_alias, title, content):
    '''
    Utility to send mail

    :param sender: string, the email address of the sender
    :param sender_alias: string, the alias of the sender name
    :param password: string, the password or token of the sender's email
    :param server: string, the smtp domain of sender's email
    :param port: int, the port no of smtp service
    :param user: string, the receiver email address
    :param user_alias: string, the name of the receiver
    :param title: string, the title of the email
    :param content: string, the content of the email
    :return: boolen, true for success sending
    '''
    ret = True
    try:
        msg = MIMEText(content, 'html', 'utf-8')
        msg['From'] = formataddr([sender_alias, sender])
        msg['To'] = formataddr([user_alias, user])
        msg['Subject'] = title

        server = smtplib.SMTP_SSL(server, port)
        server.login(sender, password)
        server.sendmail(sender, [user], msg.as_string())
        server.quit()
    except Exception:
        ret = False
    return ret