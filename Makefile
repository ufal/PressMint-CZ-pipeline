.DEFAULT_GOAL := help

.PHONY: help
## help ## print this help
help:
	echo "TODO"

collection_dailyPressCollection := e8f61172-5e38-43bc-88ed-8737fc210bfc
collection_localPressCollection := 9df7d62c-b572-4338-a0d1-b9c63e07a26e
collections := $(collection_dailyPressCollection) $(collection_localPressCollection)

get-collections-UUID = $(addprefix get-collections-, $(collections))
get-collections: $(get-collections-UUID)
$(get-collections-UUID): get-collections-%: Data/collection
	curl 'https://api.kramerius.mzk.cz/search/api/client/v7.0/search?q=*:*&fq=(model:periodical)%20AND%20(in_collections.direct:%22uuid:$*%22)%20AND%20(accessibility:public)&fl=*&sort=created%20desc&rows=999&start=0' -H 'accept: application/json, text/plain, */*' \
	  > Data/collection/$*.json
		cat Data/collection/$*.json|jq -r '.response.docs[]|."root.pid"| sub("^uuid:"; "")' \
		> Data/collection/$*.uuid
		make get-periodicals collection_uuid=Data/collection/$*.uuid

Data/collection Data/periodical:
	mkdir -p $@

# create collection containing dailyPress, but not localPress
Data/collection/PressMint-CZ-collection.json:
	jq -R -s 'split("\n") | map(select(. != ""))' Data/collection/9df7d62c-b572-4338-a0d1-b9c63e07a26e.uuid > /tmp/excluded.json && \
	jq --slurpfile excluded  /tmp/excluded.json  \
		  '.response.docs |= map(select((.["root.pid"]| sub("^uuid:"; "")) as $$id | $$excluded[0] | index($$id) | not))' \
			Data/collection/$(collection_dailyPressCollection).json \
			> $@

create-custom-collection: Data/collection/PressMint-CZ-collection.json
		cat $<|jq -r '.response.docs[]|."root.pid"| sub("^uuid:"; "")' \
		> Data/collection/PressMint-CZ-collection.uuid

Data/PressMint-CZ-issues.json:
	cat DataManual/issues.json |jq '.issues |= map(select(.include == true))' > $@
Data/PressMint-CZ-issues.uuid: Data/PressMint-CZ-issues.json
	jq -r '.issues[]|.uuid' $< > $@
filter-issues: Data/PressMint-CZ-issues.uuid

get-PressMint-CZ-periodicals: Data/PressMint-CZ-issues.uuid
	make get-periodicals collection_uuid=$<

collection_uuid := 
periodicals := $(shell test -f "$(collection_uuid)" && cat $(collection_uuid) | tr "\n" " ")
collection := $(basename $(notdir $(collection_uuid)))
# loop periodical(issues) to get volumes
get-periodicals-UUID = $(addprefix get-periodicals-, $(periodicals))
get-periodicals: $(get-periodicals-UUID)
$(get-periodicals-UUID): get-periodicals-%: Data/periodical
	test -f Data/periodical/$*.json \
	|| curl 'https://api.kramerius.mzk.cz/search/api/client/v7.0/search?q=(model:periodicalvolume)%20AND%20(own_parent.pid:uuid%5C:$*)%20AND%20(licenses:public)&fl=*&sort=date.min%20asc&rows=999&start=0' -H 'accept: application/json, text/plain, */*' \
	> Data/periodical/$*.json \
	&& cat Data/periodical/$*.json|jq -r '.response.docs[]|.pid| sub("^uuid:"; "")' \
	> Data/periodical/$*.uuid \
	&& make get-periodicalvolumes periodical_uuid=Data/periodical/$*.uuid


periodical_uuid := 
periodicalvolumes := $(shell test -f "$(periodical_uuid)" && cat $(periodical_uuid) | tr "\n" " ")
periodical := $(basename $(notdir $(periodical_uuid)))

Data/periodical/$(periodical):
	mkdir -p $@
# loop volumes to get items(copies)
get-periodicalvolumes-UUID = $(addprefix get-periodicalvolumes-, $(periodicalvolumes))
get-periodicalvolumes: $(get-periodicalvolumes-UUID)
$(get-periodicalvolumes-UUID): get-periodicalvolumes-%: Data/periodical/$(periodical)
	test -f Data/periodical/$(periodical)/$*.json \
	|| curl 'https://api.kramerius.mzk.cz/search/api/client/v7.0/search?q=(model:periodicalitem)%20AND%20(own_parent.pid:uuid%5C:$*)%20AND%20(licenses.facet:public%20OR%20licenses:public%20OR%20licenses_of_ancestors:public)&fl=*&sort=date.min%20asc&rows=999&start=0' -H 'accept: application/json, text/plain, */*'  \
	> Data/periodical/$(periodical)/$*.json
	cat Data/periodical/$(periodical)/$*.json|jq -r '.response.docs[]|.pid| sub("^uuid:"; "")' \
	> Data/periodical/$(periodical)/$*.uuid
	make get-periodicalitems periodical=$(periodical) periodicalvolume_uuid=Data/periodical/$(periodical)/$*.uuid




periodicalvolume_uuid := 
periodicalitems := $(shell test -f "$(periodicalvolume_uuid)" && cat $(periodicalvolume_uuid) | tr "\n" " ")
periodicalvolume := $(basename $(notdir $(periodicalvolume_uuid)))

Data/periodical/$(periodical)/$(periodicalvolume):
	mkdir -p $@
# loop items(copies) to get pages
get-periodicalitems-UUID = $(addprefix get-periodicalitems-, $(periodicalitems))
get-periodicalitems: $(get-periodicalitems-UUID)
$(get-periodicalitems-UUID): get-periodicalitems-%: Data/periodical/$(periodical)/$(periodicalvolume)
	test -f Data/periodical/$(periodical)/$(periodicalvolume)/$*.json \
	|| curl 'https://api.kramerius.mzk.cz/search/api/client/v7.0/search?q=(own_parent.pid:uuid%5C:$*)&fl=*&sort=rels_ext_index.sort%20asc&rows=999&start=0' -H 'accept: application/json, text/plain, */*'  \
	> Data/periodical/$(periodical)/$(periodicalvolume)/$*.json
	cat Data/periodical/$(periodical)/$(periodicalvolume)/$*.json|jq -r '.response.docs[]|.pid| sub("^uuid:"; "")' \
	> Data/periodical/$(periodical)/$(periodicalvolume)/$*.uuid
	make get-page-ocr-texts periodical=$(periodical) periodicalvolume=$(periodicalvolume) periodicalitem_uuid=Data/periodical/$(periodical)/$(periodicalvolume)/$*.uuid


# loop pages to get ocr text

periodicalitem_uuid := 
pages := $(shell test -f "$(periodicalitem_uuid)" && cat $(periodicalitem_uuid) | tr "\n" " ")
periodicalitem := $(basename $(notdir $(periodicalitem_uuid)))

Data/periodical/$(periodical)/$(periodicalvolume)/$(periodicalitem):
	mkdir -p $@
get-page-ocr-texts-UUID = $(addprefix get-page-ocr-texts-, $(pages))
get-page-ocr-texts: $(get-page-ocr-texts-UUID)
$(get-page-ocr-texts-UUID): get-page-ocr-texts-%: Data/periodical/$(periodical)/$(periodicalvolume)/$(periodicalitem)
	test -f Data/periodical/$(periodical)/$(periodicalvolume)/$(periodicalitem)/$*.txt \
	|| curl 'https://api.kramerius.mzk.cz/search/api/client/v7.0/items/uuid:$*/ocr/text' -H 'accept: application/json, text/plain, */*' \
	> Data/periodical/$(periodical)/$(periodicalvolume)/$(periodicalitem)/$*.txt


# loop pages to get metadata
# loop pages to get fascimiles

#
uuid2url:
	echo "TODO: not implemented $@"



stats-copies:
	@echo -e "id_issue\tid_volume\tid_copy\ttitle\tdate\tlanguages\tpages\twords" \
	> DataStats/stats-copies.tsv
	@for file in `find Data/periodical  -mindepth 2 -maxdepth 2 -type f -name "*.json"`; do \
	jq -r '.response.docs[]|"\(.own_pid_path)\t\(.["root.title"])\t\(.["date.min"] | split("T")[0])\t\(.["languages.facet"])\t\(.["count_page"])\t"' $${file}\
	  | sed "s@/uuid:@\t@g;s/^uuid://" \
	  | while IFS= read -r line; do \
		  words=$$(cat $$(echo "$${line}"|cut -f1,2,3|tr "\t" "/"|sed 's@^@Data/periodical/@;s@$$@/*.txt@')| wc -w);\
			echo "$${line}$${words}"| tr -d '"[]';\
		done;\
	done \
	>> DataStats/stats-copies.tsv

stats-periodicalvolumesQ:
	cat DataStats/stats-copies.tsv | awk -F'\t' 'BEGIN { OFS = FS } NR==1{print; next} { split($$5,d,"-"); $$5=d[1]"Q"int((d[2]-1)/3+1); print }' | cut -f1,2,4,5,7,8 | { read -r header; echo "$$header"; cat | datamash -t$$'\t' -g 1,2,3,4 sum 5 sum 6; } \
	> DataStats/stats-periodicalvolumesQ.tsv