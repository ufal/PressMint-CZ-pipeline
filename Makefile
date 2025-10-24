.DEFAULT_GOAL := help


SAMPLE ?= 0
DATA ?= $(shell pwd)/Data/
SAMPLE_SOURCE_SOURCE = $(shell pwd)/Data/source
SAMPLE_UUIDs_FILE = $(shell pwd)/DataManual/sample-issues.paths.uuid
ifeq ($(SAMPLE),1)
DATA := $(shell pwd)/Sample/
endif

IN := ${DATA}source
WORK := ${DATA}work
DIST := ${DATA}dist

ifdef UUID_PATH

periodical := $(shell echo "$(UUID_PATH)"| cut -d '/' -f 1)
periodicalvolume := $(shell echo "$(UUID_PATH)"| cut -d '/' -f 2)
periodicalitem := $(shell echo "$(UUID_PATH)"| cut -d '/' -f 3)
page := $(shell echo "$(UUID_PATH)"| cut -d '/' -f 4)

periodicals := $(periodical)
periodicalvolumes := $(periodicalvolume)
periodicalitems := $(periodicalitem)
pages := $(page)

else
collection_uuid := 
periodicals := $(shell test -f "$(collection_uuid)" && cat $(collection_uuid) | tr "\n" " ")
collection := $(basename $(notdir $(collection_uuid)))

periodical_uuid := 
periodicalvolumes := $(shell test -f "$(periodical_uuid)" && cat $(periodical_uuid) | tr "\n" " ")
periodical := $(basename $(notdir $(periodical_uuid)))

periodicalvolume_uuid := 
periodicalitems := $(shell test -f "$(periodicalvolume_uuid)" && cat $(periodicalvolume_uuid) | tr "\n" " ")
periodicalvolume := $(basename $(notdir $(periodicalvolume_uuid)))

periodicalitem_uuid := 
pages := $(shell test -f "$(periodicalitem_uuid)" && cat $(periodicalitem_uuid) | tr "\n" " ")
periodicalitem := $(basename $(notdir $(periodicalitem_uuid)))
endif

.PHONY: help
## help ## print this help
help:
	echo "TODO"

-include Makefile.dev
-include Makefile.deprecated

ifneq ($(SAMPLE),1)
$(IN)/PressMint-CZ-issues.json: $(IN)
	cat DataManual/issues.json |jq '.issues |= map(select(.include == true))' > $@

$(IN)/PressMint-CZ-issues.uuid: $(IN)/PressMint-CZ-issues.json
	jq -r '.issues[]|.uuid' $< > $@
filter-issues: $(IN)/PressMint-CZ-issues.uuid
endif


# PressMint data gathering starting point
get-PressMint-CZ-periodicals: $(IN)/PressMint-CZ-issues.uuid
ifeq ($(SAMPLE),1)
	@echo "Skipping data downloading: SAMPLE mode active."
	make get-PressMint-CZ-sample-periodicals
else	
	make get-periodicals collection_uuid=$<
endif

get-PressMint-CZ-sample-periodicals:
ifeq ($(SAMPLE),1)
	for p in `cat $(SAMPLE_UUIDs_FILE)`; \
	do \
	  mkdir -p $(IN)/periodical/$$p; \
	  cp -r $(SAMPLE_SOURCE_SOURCE)/periodical/$$p/* $(IN)/periodical/$$p/; \
		path=""; \
		for uuid in `echo "$$p" | tr '/' ' '` ; \
		do \
		  path="$${path:+$$path/}$$uuid"; \
		  jq . $(SAMPLE_SOURCE_SOURCE)/periodical/$$path.json > $(IN)/periodical/$$path.json ; \
		done; \
		find $(IN)/periodical/$$p -type f -name "*.txt" \
		  | sed 's@^.*periodical/\(.*\).txt$$@make SAMPLE=1 get-page-image UUID_PATH=\1@'| sh ; \
	done
else	
	@echo "Available only in SAMPLE mode."
endif


# loop periodical(issues) to get volumes
get-periodicals-UUID = $(addprefix get-periodicals-, $(periodicals))
get-periodicals: $(get-periodicals-UUID)
$(get-periodicals-UUID): get-periodicals-%: $(IN)/periodical
ifeq ($(SAMPLE),1)
	@echo "Skipping data downloading: SAMPLE mode active."
else	
	test -f $(IN)/periodical/$*.json \
	|| curl 'https://api.kramerius.mzk.cz/search/api/client/v7.0/search?q=(model:periodicalvolume)%20AND%20(own_parent.pid:uuid%5C:$*)%20AND%20(licenses:public)&fl=*&sort=date.min%20asc&rows=999&start=0' -H 'accept: application/json, text/plain, */*' \
	> $(IN)/periodical/$*.json \
	&& cat $(IN)/periodical/$*.json|jq -r '.response.docs[]|.pid| sub("^uuid:"; "")' \
	> $(IN)/periodical/$*.uuid \
	&& make get-periodicalvolumes periodical_uuid=$(IN)/periodical/$*.uuid
endif



$(IN)/periodical/$(periodical):
	mkdir -p $@
# loop volumes to get items(copies)
get-periodicalvolumes-UUID = $(addprefix get-periodicalvolumes-, $(periodicalvolumes))
get-periodicalvolumes: $(get-periodicalvolumes-UUID)
$(get-periodicalvolumes-UUID): get-periodicalvolumes-%: $(IN)/periodical/$(periodical)
	test -f $(IN)/periodical/$(periodical)/$*.json \
	|| curl 'https://api.kramerius.mzk.cz/search/api/client/v7.0/search?q=(model:periodicalitem)%20AND%20(own_parent.pid:uuid%5C:$*)%20AND%20(licenses.facet:public%20OR%20licenses:public%20OR%20licenses_of_ancestors:public)&fl=*&sort=date.min%20asc&rows=999&start=0' -H 'accept: application/json, text/plain, */*'  \
	> $(IN)/periodical/$(periodical)/$*.json
	cat $(IN)/periodical/$(periodical)/$*.json|jq -r '.response.docs[]|.pid| sub("^uuid:"; "")' \
	> $(IN)/periodical/$(periodical)/$*.uuid
	make get-periodicalitems periodical=$(periodical) periodicalvolume_uuid=$(IN)/periodical/$(periodical)/$*.uuid




$(IN)/periodical/$(periodical)/$(periodicalvolume):
	mkdir -p $@
# loop items(copies) to get pages
get-periodicalitems-UUID = $(addprefix get-periodicalitems-, $(periodicalitems))
get-periodicalitems: $(get-periodicalitems-UUID)
$(get-periodicalitems-UUID): get-periodicalitems-%: $(IN)/periodical/$(periodical)/$(periodicalvolume)
	test -f $(IN)/periodical/$(periodical)/$(periodicalvolume)/$*.json \
	|| curl 'https://api.kramerius.mzk.cz/search/api/client/v7.0/search?q=(own_parent.pid:uuid%5C:$*)&fl=*&sort=rels_ext_index.sort%20asc&rows=999&start=0' -H 'accept: application/json, text/plain, */*'  \
	> $(IN)/periodical/$(periodical)/$(periodicalvolume)/$*.json
	cat $(IN)/periodical/$(periodical)/$(periodicalvolume)/$*.json|jq -r '.response.docs[]|.pid| sub("^uuid:"; "")' \
	> $(IN)/periodical/$(periodical)/$(periodicalvolume)/$*.uuid
	make get-page-ocr-texts periodical=$(periodical) periodicalvolume=$(periodicalvolume) periodicalitem_uuid=$(IN)/periodical/$(periodical)/$(periodicalvolume)/$*.uuid


# loop pages to get ocr text
$(IN)/periodical/$(periodical)/$(periodicalvolume)/$(periodicalitem):
	mkdir -p $@
get-page-ocr-texts-UUID = $(addprefix get-page-ocr-texts-, $(pages))
get-page-ocr-texts: $(get-page-ocr-texts-UUID)
$(get-page-ocr-texts-UUID): get-page-ocr-texts-%: $(IN)/periodical/$(periodical)/$(periodicalvolume)/$(periodicalitem)
	test -f $(IN)/periodical/$(periodical)/$(periodicalvolume)/$(periodicalitem)/$*.txt \
	|| curl 'https://api.kramerius.mzk.cz/search/api/client/v7.0/items/uuid:$*/ocr/text' -H 'accept: application/json, text/plain, */*' \
	> $(IN)/periodical/$(periodical)/$(periodicalvolume)/$(periodicalitem)/$*.txt


# loop pages to get metadata
# loop pages to get fascimiles
get-page-image-UUID = $(addprefix get-page-image-, $(pages))
get-page-image: $(get-page-image-UUID)
$(get-page-image-UUID): get-page-image-%: $(IN)/periodical/$(periodical)/$(periodicalvolume)/$(periodicalitem)
	test -f $(IN)/periodical/$(periodical)/$(periodicalvolume)/$(periodicalitem)/$*.jpg \
	|| curl 'https://api.kramerius.mzk.cz/search/iiif/uuid:$*/full/max/0/default.jpg' \
	> $(IN)/periodical/$(periodical)/$(periodicalvolume)/$(periodicalitem)/$*.jpg

#
uuid2url:
	echo "TODO: not implemented $@"



stats-copies:
	@echo "id_issue\tid_volume\tid_copy\ttitle\tdate\tlanguages\tpages\twords" \
	> DataStats/stats-copies.tsv
	@for file in `find $(IN)/periodical  -mindepth 2 -maxdepth 2 -type f -name "*.json"`; do \
	jq -r '.response.docs[]|"\(.own_pid_path)\t\(.["root.title"])\t\(.["date.min"] | split("T")[0])\t\(.["languages.facet"])\t\(.["count_page"])\t"' $${file}\
	  | sed "s@/uuid:@\t@g;s/^uuid://" \
	  | while IFS= read -r line; do \
		  words=$$(cat $$(echo "$${line}"|cut -f1,2,3|tr "\t" "/"|sed 's@^@$(IN)/periodical/@;s@$$@/*.txt@')| wc -w);\
			echo "$${line}$${words}"| tr -d '"[]';\
		done;\
	done \
	>> DataStats/stats-copies.tsv

stats-periodical:
	@TAB=$$(printf '\t'); \
	cat DataStats/stats-copies.tsv | cut -f1,4,7,8 | { read -r header; echo "$$header"; cat | datamash -t"$$TAB" -g 1,2 sum 3 sum 4; } \
	> DataStats/stats-periodical.tsv

stats-periodicalvolumesQ:
	@TAB=$$(printf '\t'); \
	cat DataStats/stats-copies.tsv | awk -F"$$TAB" 'BEGIN { OFS = FS } NR==1{print; next} { split($$5,d,"-"); $$5=d[1]"Q"int((d[2]-1)/3+1); print }' | cut -f1,2,4,5,7,8 | { read -r header; echo "$$header"; cat | datamash -t"$$TAB" -g 1,2,3,4 sum 5 sum 6; } \
	> DataStats/stats-periodicalvolumesQ.tsv

stats-periodicalvolumes:
	@TAB=$$(printf '\t'); \
	cat DataStats/stats-copies.tsv | awk -F"$$TAB" 'BEGIN { OFS = FS } NR==1{print; next} { split($$5,d,"-"); $$5=d[1]; print }' | cut -f1,2,4,5,7,8 | { read -r header; echo "$$header"; cat | datamash -t"$$TAB" -g 1,2,3,4 sum 5 sum 6; } \
	> DataStats/stats-periodicalvolumes.tsv

chart-periodicalvolumes:
	bash ./Scripts/plot-stackedbar.sh -i DataStats/stats-periodicalvolumes.tsv -o DataStats/chart-year-word-issue.png -m words