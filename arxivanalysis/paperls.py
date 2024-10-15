"""
keyword based match for arxiv content
"""

from fuzzywuzzy import fuzz
import requests
from bs4 import BeautifulSoup
import re
from datetime import date, timedelta
from arxivanalysis.arxiv import query
from arxivanalysis.notification import sendmail, makemailcontent
from datetime import datetime
from arxivanalysis.rake import Rake
from arxivanalysis.cons import weekdaylist, category


class arxivException(Exception):
    pass


class Paperls:
    """
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
    """

    def __init__(
        self,
        search_mode=1,
        search_query="",
        id_list=[],
        start=0,
        max_results=10,
        sort_by="relevance",
        sort_order="descending",
    ):
        if search_mode == 1:  # API case
            self.url, self.contents = query(
                search_query=search_query,
                id_list=id_list,
                start=start,
                max_results=max_results,
                sort_by=sort_by,
                sort_order=sort_order,
            )
            idextract = re.compile(".*/([0-9.]*)")
            for c in self.contents:
                c["title"] = re.subn(r"\n|  ", " ", c.get("title", ""))[0]
                c["title"] = re.subn(r"  ", " ", c.get("title", ""))[0]
                c["summary"] = re.subn(r"\n|  ", " ", c.get("summary", ""))[0]
                c["summary"] = re.subn(r"  ", " ", c.get("summary", ""))[0]
                c["arxiv_id"] = idextract.match(c["arxiv_url"]).group(1)
                c["subject_abbr"] = [
                    d["term"] for d in c["tags"] if d["term"] in category
                ]
                c["subject"] = [
                    category.get(d, "") + " (%s)" % d for d in c["subject_abbr"]
                ]
                c["announce_date"] = announce_date_converter(c["published_parsed"])
        elif search_mode == 2:  # new submission fetch
            self.url = "https://arxiv.org/list/" + search_query + "/new"
            samedate = False
            if sort_by == "submittedDate":
                samedate = True
            self.contents = new_submission(self.url, mode=start, samedate=samedate)

        self.count = 0
        self.search_query = search_query

    def merge(self, paperlsobj):
        """
        merge other paper list

        :param paperlsobj:
        :return:
        """
        idlist = [c["arxiv_id"] for c in self.contents]
        for c in paperlsobj.contents:
            if c["arxiv_id"] not in idlist:
                self.contents.append(c)

    def interest_match(self, choices):
        contents = self.contents
        for content in contents:
            content["keyword"] = keyword_match(
                content["title"]
                + ". "
                + content["title"]
                + ". "
                + ",".join(content["authors"])
                + ". "
                + content["summary"],
                choices,
            )
            content["weight"] = sum([choices[kw[0]] for kw in content["keyword"]])

    def tagging(self, stoplistpath="SmartStopList.txt"):
        rake = Rake(stoplistpath)
        for content in self.contents:
            content["tags"] = deduplicate_tags(
                select_tags(
                    rake.run(
                        content["title"]
                        + ". "
                        + content["summary"]
                        + " "
                        + content["title"]
                    )
                )
            )

    def show_relevant(self, purify=False):
        contents = self.contents
        if not purify:
            return sorted(
                [c for c in contents if c.get("keyword", None)],
                key=lambda s: s["weight"],
                reverse=True,
            )
        else:
            pcontents = []
            for c in contents:
                if c.get("keyword", None):
                    pcontent = {}
                    pcontent["arxiv_id"] = c.get("arxiv_id", None)
                    pcontent["arxiv_url"] = c.get("arxiv_url", None)
                    pcontent["title"] = c.get("title", None)
                    pcontent["authors"] = c.get("authors", None)
                    pcontent["subject"] = c.get("subject", None)
                    pcontent["subject_abbr"] = c.get("subject_abbr", None)
                    pcontent["summary"] = c.get("summary", None)
                    pcontent["keyword"] = c.get("keyword", None)
                    pcontent["weight"] = c.get("weight", None)
                    pcontent["tags"] = select_tags(
                        c.get("tags", None), max_num=5, threhold=7.9
                    )
                    pcontent["announce_date"] = c.get("announce_date", None)
                    pcontents.append(pcontent)
            return sorted(pcontents, key=lambda s: s["weight"], reverse=True)

    def mail(
        self,
        maildict,
        headline="Below is the summary of highlights on arXiv based on your interests",
    ):
        rs = self.show_relevant(purify=True)
        if rs:
            maildict["content"] = makemailcontent(headline, rs)
            maildict["title"] = "Report on highlight of arXiv"
            ret = sendmail(**maildict)
            if not ret:
                raise arxivException("mail sending failed")

    def __iter__(self):
        return self

    def __next__(self):
        if self.count >= len(self.contents):
            self.count = 0
            raise StopIteration
        else:
            self.count += 1
            return self.contents[self.count - 1]


def keyword_match(text, kwlist, threhold=(90, 80)):
    r = []
    for kw in kwlist:
        tsr_score = fuzz.token_set_ratio(kw, text)
        pr_score = fuzz.partial_ratio(kw, text)
        if tsr_score > threhold[0] or pr_score > threhold[1]:
            r.append((kw, tsr_score, pr_score))
    # note the issue on which matching function to use here
    return r


def new_submission(url, mode=1, samedate=False):
    """
    fetching new submission everyday

    :param url: string, the url for the new page of certain category
    :param mode: int, 0 for new, 1 for cross, 2 for both
    :param samedate: boolean, if true, there is a check to make sure the submission is for today
    :return: list of dict, containing all papers
    """
    pa = requests.get(url)
    so = BeautifulSoup(pa.text, "lxml")
    if samedate is True:
        date_filter = re.compile(r"^Showing new listings for ([a-zA-Z]+), .*")
        try:
            print(so("h3")[0])
            weekdaystr = date_filter.match(so("h3")[0].string).group(1)
        except AttributeError:
            return []
        if weekdaylist[datetime.today().weekday()] != weekdaystr[:3]:
            return []

    submission_pattern = re.compile(r"(.*) \(showing .*")
    submission_list = so("h3")
    submission_dict = {}
    for s in submission_list[1:]:
        dict_key = submission_pattern.match(s.string).group(1)
        submission_dict[dict_key] = True

    if mode == 0 and submission_dict.get("New submissions", False):
        newc = so("dl")[0]
    elif mode == 1 and submission_dict.get("Cross-lists", False):
        newc = so("dl")[1]
    elif submission_dict.get("New submissions", False) and submission_dict.get(
        "Cross-lists", False
    ):
        newc = BeautifulSoup(str(so("dl")[0]) + str(so("dl")[1]), "lxml")
    else:
        return []

    # newno = len(newc("div", class_="list-title"))

    contents = []
    subjectabbr_filter = re.compile(r"^.*[(](.*)[)]")
    ##  old version before 24.05
    # newno = len(newc("span", class_="list-identifier"))
    # for i in range(newno):
    #     content = {}
    #     id_ = list(newc("span", class_="list-identifier")[i].children)[0].text
    #     content["arxiv_id"] = re.subn(r"arXiv:", "", id_)[0]
    #     content["arxiv_url"] = "https://arxiv.org/abs/" + content["arxiv_id"]
    #     title = newc("div", class_="list-title mathjax")[i].text
    #     content["title"] = re.subn(r"\n|Title: ", "", title)[0]
    #     author = newc("div", class_="list-authors")[i].text
    #     content["authors"] = [
    #         re.subn(r"\n|Authors:", "", author)[0].strip()
    #         for author in author.split(",")
    #     ]
    #     subject = newc("div", class_="list-subjects")[i].text
    #     content["subject"] = [
    #         re.subn(r"\n|Subjects: ", "", sub.strip())[0] for sub in subject.split(r";")
    #     ]
    #     content["subject_abbr"] = [
    #         subjectabbr_filter.match(d).group(1) for d in content["subject"]
    #     ]
    #     abstract = newc("p", class_="mathjax")[i].text
    #     content["summary"] = re.subn(r"\n", " ", abstract)[0]
    #     content["announce_date"] = date.today().strftime("%Y-%m-%d")
    #     contents.append(content)

    ## new crawler version for new arxiv html after 24.05, assisted by kimi
    for item in newc.find_all("dd"):
        dt_tag = item.find_previous("dt")
        content = {}

        # Extract the arXiv ID and URL
        arxiv_id_link = dt_tag.find("a", href=True)
        content["arxiv_id"] = re.sub(r"^/abs/", "", arxiv_id_link["href"])
        content["arxiv_url"] = f"https://arxiv.org/abs/{content['arxiv_id']}"

        # Extract the title
        title = item.find("div", class_="list-title mathjax").text
        content["title"] = re.sub(r"\n|Title:", "", title).strip()

        # Extract authors
        authors_div = item.find("div", class_="list-authors")
        authors = authors_div.text if authors_div else ""
        content["authors"] = [
            re.sub(r"\n|Authors: ", "", author).strip() for author in authors.split(",")
        ]

        # Extract subjects
        subjects_div = item.find("div", class_="list-subjects")
        subjects = subjects_div.text if subjects_div else ""
        content["subject"] = [
            re.sub(r"\n|Subjects:", "", sub.strip()) for sub in subjects.split(";")
        ]
        content["subject_abbr"] = [
            subjectabbr_filter.match(d).group(1) for d in content["subject"]
        ]

        # Extract the abstract
        abstract = item.find("p", class_="mathjax").text
        content["summary"] = re.sub(r"\n", " ", abstract).strip()

        # Set the announcement date
        content["announce_date"] = date.today().strftime("%Y-%m-%d")

        # Append the content dictionary to the contents list
        contents.append(content)
    return contents


def select_tags(kw_rank, max_num=10, threhold=3.9):
    if kw_rank is None:
        return []
    high_res = [c for c in kw_rank if c[1] > threhold]
    if len(high_res) == 0:
        return [kw_rank[0]]
    elif len(high_res) <= max_num:
        return high_res
    else:
        return high_res[:max_num]


def deduplicate_tags(kw_rank, threhold=65):
    len_kw = len(kw_rank)
    mask = [True for _ in range(len_kw)]
    for i in range(len_kw):
        if mask[i] is True:
            for j in range(i + 1, len_kw):
                if mask[j] is True:
                    if fuzz.partial_ratio(kw_rank[i][0], kw_rank[j][0]) > threhold:
                        if len(kw_rank[i][0]) > len(kw_rank[j][0]):
                            mask[i] = False
                            break
                        else:
                            mask[j] = False

    return [kw for i, kw in enumerate(kw_rank) if mask[i] is True]


def kw_lst2dict(choices):
    """
    convert list of keywords to standard dict of keywords with matching weight

    :param choices: list of strings, keywords
    :return: dict, keyword: weight
    """
    if isinstance(choices, dict):
        return choices
    kwdict = {}
    l = len(choices)
    for i, c in enumerate(choices):
        kwdict[c] = l - i
    return kwdict


def announce_date_converter(parsed_date):
    dt = date(parsed_date.tm_year, parsed_date.tm_mon, parsed_date.tm_mday)
    if parsed_date.tm_hour > 14:
        dt = dt + timedelta(days=1)
    if dt.weekday() == 5:
        dt = dt + timedelta(days=2)
    elif dt.weekday() == 6:
        dt = dt + timedelta(days=1)
    return dt.strftime("%Y-%m-%d")
