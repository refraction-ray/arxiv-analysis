## Urgent

- [x] issue when there is no replacement list
- [x] decouple keywords match and adding tags
- [ ] There is bug in terms of the implementation of `fuzz.partial_ratio()`, the result of the score is not consistent, maybe related to [this issue](https://github.com/seatgeek/fuzzywuzzy/issues/214). (It seems both `partial_ratio` and `token_set_ration` are not enough, one is too strict one is too weird). 

## Near term

- [ ] tests by pytest
- [ ] travis CI
- [ ] update README
- [ ] setup doc by sphnix
- [ ] add CHANGELOG
- [x] unfied subject key of Paperls
- [ ] auto classify the announce date of papers
- [x] link of authors

## Furture plan

- [ ] paper metadata into database
- [ ] auto generate paper-style text
- [ ] webapp for arxiv analysis
- [ ] more machine learning techinques on arxiv papers to extract hot trend
- [ ] paper relevance and recommendations