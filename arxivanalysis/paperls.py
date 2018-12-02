"""
keyword based match for arxiv content
"""

from fuzzywuzzy import fuzz
import requests
from bs4 import BeautifulSoup
import re
from arxivanalysis.arxiv import query
from arxivanalysis.notification import sendmail, makemailcontent
from datetime import datetime
from arxivanalysis.rake import Rake

weekdaylist = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

class arxivException(Exception):
    pass

class Paperls:
    '''
    Class for paper list from arxiv based on certain condition

    :param search_mode: int, 1 for arxiv API search, 2 for new submission review
    :param search_query: string, for search_query construction in mode 1, see arxiv api doc.
                        For mode 2, search_query is the category of new submission, eg. cond
    :param id_list: list for strings of arxiv id, only available for mode 1
    :param start: int, the offset of the return results in mode 1. In mode 2, start=0 for new list, 1 for cross list and 2 for both.
    :param max_results: int, the max number of return items, only available for mode 1
    :param sort_by: string, for mode 1, see arxiv api doc. for mode 2, the only available one is "submittedDate",
                    which means check the date to make sure the submission is new for today.
    :param sort_order: string, only available for mode 1, see arxiv api doc
    '''
    def __init__(self,
         search_mode = 1,
         search_query="",
         id_list=[],
         start=0,
         max_results=10,
         sort_by="relevance",
         sort_order="descending"):
        if search_mode == 1: # API case
            self.url, self.contents = query(search_query=search_query,
                                            id_list=id_list, start=start, max_results=max_results,
                                            sort_by=sort_by, sort_order=sort_order)
            idextract = re.compile('.*/([0-9.]*)')
            for c in self.contents:
                c['title'] = re.sub(r'\n|  ', ' ', c.get('title', ''))
                c['summary'] = re.sub(r'\n|  ', ' ', c.get('summary',''))
                c['arxiv_id'] = idextract.match(c['arxiv_url']).group(1)
        elif search_mode == 2: # new submission fetch
            self.url = "https://arxiv.org/list/" + search_query + "/new"
            samedate = False
            if sort_by == "submittedDate":
                samedate = True
            self.contents = new_submission(self.url, mode=start, samedate=samedate)

    def merge(self, paperlsobj):
        idlist = [c['arxiv_id'] for c in self.contents]
        for c in paperlsobj.contents:
            if c['arxiv_id'] not in idlist:
                self.contents.append(c)

    def interest_match(self, choices, stoplistpath = 'SmartStopList.txt'):
        contents = self.contents
        for content in contents:
            content['keyword'] = keyword_match(
                content['title'] + '. ' + content['title'] + '. ' + ','.join(content['authors']) + '. ' +
                content['summary'], choices)
            content['weight'] = sum([choices[kw[0]] for kw in content['keyword']])
            rake = Rake(stoplistpath)
            content['tags'] = select_tags(rake.run(content['title']+". "+content['summary']+" "+content['title']))

    def show_relevant(self, purify=False):
        contents = self.contents
        if not purify:
            return sorted([c for c in contents if c.get('keyword', None)],key=lambda s: s['weight'], reverse=True)
        else:
            pcontents = []
            for c in contents:
                if c.get('keyword', None):
                    pcontent = {}
                    pcontent['arxiv_id'] = c.get('arxiv_id', None)
                    pcontent['arxiv_url'] = c.get('arxiv_url', None)
                    pcontent['title'] = c.get('title', None)
                    pcontent['authors'] = c.get('authors', None)
                    pcontent['subject'] = c.get('subject', None)
                    pcontent['summary'] = c.get('summary', None)
                    pcontent['keyword'] = c.get('keyword', None)
                    pcontent['weight'] = c.get('weight', None)
                    pcontent['tags'] = c.get('tags', None)
                    pcontents.append(pcontent)
            return sorted(pcontents, key=lambda s: s['weight'], reverse=True)

    def mail(self, maildict, headline='Below is the summary of highlights on arXiv based on your interests'):
        rs = self.show_relevant()
        if rs:
            maildict['content'] = makemailcontent(headline, rs)
            maildict['title'] = 'Report on highlight of arXiv'
            ret = sendmail(**maildict)
            if not ret:
                raise arxivException('mail sending failed')



def keyword_match(text, kwlist, threhold=80):
    rs = [(kw, fuzz.partial_ratio(kw, text)) for kw in kwlist]
    return [r for r in rs if r[-1] > threhold]


def new_submission(url, mode=1, samedate=False):
    '''
    fetching new submission everyday

    :param url: string, the url for the new page of certain category
    :param mode: int, 0 for new, 1 for cross, 2 for both
    :param samedate: boolean, if true, there is a check to make sure the submission is for today
    :return: list of dict, containing all papers
    '''
    pa = requests.get(url)
    so = BeautifulSoup(pa.text, 'lxml')
    if samedate is True:
        date_filter = re.compile(r'^New submissions for ([a-zA-Z]+), .*')
        weekdaystr = date_filter.match(so('h3')[0].string).group(1)
        if weekdaylist[datetime.today().weekday()] != weekdaystr:
            return None
    if mode == 0:
        newc = so('dl')[0]
    elif mode == 1:
        newc = so('dl')[1]
    else:
        newc = BeautifulSoup(str(so('dl')[0]) + str(so('dl')[1]), 'lxml')

    newno = len(newc('span', class_='list-identifier'))
    contents = []
    for i in range(newno):
        content = {}
        id_ = list(newc('span', class_='list-identifier')[i].children)[0].text
        content['arxiv_id'] = re.subn(r'arXiv:', '', id_)[0]
        content['arxiv_url'] = "https://arxiv.org/abs/" + content['arxiv_id']
        title = newc('div', class_="list-title mathjax")[i].text
        content['title'] = re.subn(r'\n|Title: ', '', title)[0]
        author = newc('div', class_="list-authors")[i].text
        content['authors'] = [re.subn(r'\n|Authors:', '', author)[0].strip() for author in author.split(',')]
        subject = newc('div', class_="list-subjects")[i].text
        content['subject'] = [re.subn(r'\n|Subjects: ', '', sub.strip())[0] for sub in subject.split(r';')]
        abstract = newc('p', class_="mathjax")[i].text
        content['summary'] = re.subn(r'\n', ' ', abstract)[0]
        contents.append(content)

    return contents

def select_tags(kw_rank):
    high_res = [c[0] for c in kw_rank if c[1]>7.9]
    if len(high_res) == 0:
        return [kw_rank[0][0]]
    elif len(high_res) <= 5:
        return high_res
    else:
        return high_res[:5]