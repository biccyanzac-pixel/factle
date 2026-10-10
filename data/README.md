# Factle fact dataset

`facts.jsonl` is derived from English Wikipedia's "Did you know…?" hooks (https://en.wikipedia.org/wiki/Wikipedia:Did_you_know_archive)
and the articles they link to. Text from Wikipedia is licensed under CC BY-SA 4.0, so this derived dataset
is too: https://creativecommons.org/licenses/by-sa/4.0/ . Each fact lists its source articles (`sources[].url`);
attribution goes to the Wikipedia contributors of those articles. The facts were filtered and reworded by
automated rules (see docs/ingest.md). Wikidata data (CC0) was used to classify linked articles.
