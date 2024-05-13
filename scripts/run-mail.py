import sys

sys.path.insert(0, "./")
from arxivanalysis.paperls import Paperls, kw_lst2dict
import requests

stoppath = "./arxivanalysis/SmartStopList.txt"


def read_kw(choices):
    if isinstance(choices, dict):
        return choices
    elif isinstance(choices, list):
        return kw_lst2dict(choices)
    elif isinstance(choices, str) and len(choices) > 0:
        wordlist = []
        with open(choices, "r") as datafile:
            for line in datafile:
                wordlist.append(line)
        return kw_lst2dict(wordlist)
    else:
        return {}


_paper_ls_dict = {}


def curl_config():
    url = sys.argv[1]
    r = requests.get(url)
    with open("config.py", "wb") as f:
        f.write(r.content)


def main():
    from config import maildict
    from config import userdata

    sendmail, password = sys.argv[2:]
    maildict.update({"sender": sendmail, "password": password})
    for u in userdata:
        if u["valid"] is True:
            maildict["user"] = u["user"]
            maildict["user_alias"] = u["user_alias"]
            choices = read_kw(u["choices"])
            lst = Paperls(search_mode=2)
            for sub in u["subjects"]:
                if sub in _paper_ls_dict:
                    lst.merge(_paper_ls_dict[sub])
                else:
                    pl = Paperls(
                        search_mode=2,
                        search_query=sub,
                        start=0,
                        sort_by="submittedDate",
                    )
                    pl.tagging(stoppath)
                    _paper_ls_dict[sub] = pl
                    lst.merge(_paper_ls_dict[sub])
            lst.interest_match(choices)
            # print(lst.contents)
            lst.mail(maildict)


if __name__ == "__main__":
    curl_config()
    main()
