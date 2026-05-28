.DEFAULT_GOAL := help

VENV_DIR=.venv
export PATH := $(abspath $(VENV_DIR)/bin):$(PATH)

-include .env
export

DEVICE = cpu

FLEXIPIPE = ../flexipipe/.venv/bin/python -m flexipipe

PERO_OCR_COMMIT := b5ced044e7f6e44f34b257ed75a527f01f91b482
PERO_OCR_STAMP = $(VENV_DIR)/.pero-ocr-$(PERO_OCR_COMMIT)

PERO_OCR_DEVICE := $(DEVICE)
PERO_OCR_MODEL_URL := https://nextcloud.fit.vutbr.cz/public.php/dav/files/NtAbHTNkZFpapdJ
PERO_OCR_MODEL_NAME := pero_eu_cz_print_newspapers_2022-09-26
PERO_OCR_MODEL_ARCHEXT := zip
PERO_OCR_MODEL_CONFIG := Models/$(PERO_OCR_MODEL_NAME)/config_cpu.ini


# https://nextcloud.fit.vutbr.cz/s/6jNgze6fLYXQBgq?dir=/textbite/models
# https://nextcloud.fit.vutbr.cz/public.php/dav/files/6jNgze6fLYXQBgq/textbite/models/yolo-m-1200.pt
YOLO_MODEL := Models/textbite/yolo-m-1200.pt


PERLBREW_ROOT=~/perl5/perlbrew
PERL := $(shell test -n "$(USE_PERL)" && echo -n "$(PERLBREW_ROOT)/perls/$(USE_PERL)/bin/perl" || echo -n "perl")

##$SAMPLE## Set to 1 to use sample data instead of full data
SAMPLE ?= 0

##$DATA## Base directory for data processing (default: ./Data, when SAMPLE=1 then ./Sample)
DATA ?= $(shell pwd)/Data/
SAMPLE_SOURCE_SOURCE = $(shell pwd)/Data/source

##$SAMPLE_UUIDs_FILE## File containing UUIDs of samples to process
SAMPLE_UUIDs_FILE = $(shell pwd)/DataManual/sample-issues.paths.uuid
ifeq ($(SAMPLE),1)
DATA := $(shell pwd)/Sample/
endif

CONFIG := $(shell pwd)/DataManual/config_PressMint-CZ.xml

IN := ${DATA}source
WORK := ${DATA}work
VIZ := ${DATA}viz
DIST := ${DATA}dist

JSONissues := ${WORK}/json-issues
idMapping := ${WORK}/idMapping
TEIheader := ${WORK}/tei-header
xmlOCR := ${WORK}/ocrXML
altoOCR := ${WORK}/ocrALTO
vizOCR := ${VIZ}/ocr
vizOCRxml := $(vizOCR)-xml
vizLAYOUT := ${VIZ}/layout
vizLAYOUTxml := $(vizLAYOUT)-xml
vizLAYOUTalto := $(vizLAYOUT)-alto
vizLAYOUTregions := $(vizLAYOUT)-regions
vizLAYOUTmerge := $(vizLAYOUT)-all
vizTEI := ${VIZ}/tei

CACHE := ${WORK}/cache

imageRegions := ${WORK}/imageRegions
TEIFacsText := ${WORK}/teiFacsText
TEIFacsTT := ${WORK}/teiFacsTT
TEItext := ${WORK}/tei-text
TEItext_cleaned := ${WORK}/tei-text-cleaned
TEIANAtext := ${WORK}/tei-ana-text
TEI := ${DIST}/tei
TEIANA := ${DIST}/tei-ana
UDPIPE := ${WORK}/udpipe
NAMETAG := ${WORK}/nametag
CORPUS_TEMPLATE := $(WORK)/PressMint-CZ.xml

LOGDIR := $(shell pwd)/Logs/
TAXONOMIES :=$(shell pwd)/DataManual/Taxonomies/

JAVA-MEMORY =
JM := $(shell test -n "$(JAVA-MEMORY)" && echo -n "-Xmx$(JAVA-MEMORY)g")
JAVA-MEMORY-GB = $(shell java $(JM) -XX:+PrintFlagsFinal -version 2>&1| grep " MaxHeapSize"|sed "s/^.*= *//;s/ .*$$//"|awk '{print "\t" $$1/1024/1024/1024}')
SAXON := java $(JM) -jar Scripts/bin/saxon.jar


ifdef UUID_PATH

periodical := $(shell echo "$(UUID_PATH)"| cut -d '/' -f 1)
periodicalvolume := $(shell echo "$(UUID_PATH)"| cut -d '/' -f 2)
periodicalitem := $(shell echo "$(UUID_PATH)"| cut -d '/' -f 3)
page := $(shell echo "$(UUID_PATH)"| cut -d '/' -f 4)

periodicals := $(periodical)
periodicalvolumes := $(periodicalvolume)
periodicalitems := $(periodicalitem)
pages := $(page)

UUID_PATH_LEVEL := $(shell echo "$(UUID_PATH)"|tr -cd '/' | wc -c)

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


-include Makefile.dev
-include Makefile.deprecated

ifneq ($(SAMPLE),1)
$(IN)/PressMint-CZ-issues.json: $(IN)
	cat DataManual/issues.json |jq '.issues |= map(select(.include == true))' > $@

$(IN)/PressMint-CZ-issues.uuid: $(IN)/PressMint-CZ-issues.json
	jq -r '.issues[]|.uuid' $< > $@
filter-issues: $(IN)/PressMint-CZ-issues.uuid
endif

###### data downloading

# PressMint data gathering starting point
## get-PressMint-CZ-periodicals ## starting point for getting data 
#### when SAMPLE=1, it will get only sample data defined in $(SAMPLE_UUIDs_FILE) 
#### otherwise all data derived from DataManual/issues.json where include == true is used)
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


##get-periodicals## loop periodical(issues) to get volumes
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
##get-periodicalvolumes## loop volumes to get items(copies)
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
##get-periodicalitems## loop items(copies) to get pages
get-periodicalitems-UUID = $(addprefix get-periodicalitems-, $(periodicalitems))
get-periodicalitems: $(get-periodicalitems-UUID)
$(get-periodicalitems-UUID): get-periodicalitems-%: $(IN)/periodical/$(periodical)/$(periodicalvolume)
	test -f $(IN)/periodical/$(periodical)/$(periodicalvolume)/$*.json \
	|| curl 'https://api.kramerius.mzk.cz/search/api/client/v7.0/search?q=(own_parent.pid:uuid%5C:$*)&fl=*&sort=rels_ext_index.sort%20asc&rows=999&start=0' -H 'accept: application/json, text/plain, */*'  \
	> $(IN)/periodical/$(periodical)/$(periodicalvolume)/$*.json
	cat $(IN)/periodical/$(periodical)/$(periodicalvolume)/$*.json|jq -r '.response.docs[]|.pid| sub("^uuid:"; "")' \
	> $(IN)/periodical/$(periodical)/$(periodicalvolume)/$*.uuid
	make get-page-ocr-texts periodical=$(periodical) periodicalvolume=$(periodicalvolume) periodicalitem_uuid=$(IN)/periodical/$(periodical)/$(periodicalvolume)/$*.uuid


##get-page-ocr-texts## loop pages to get ocr text [note: this is not used in result, because we are running custom ocrn original images]
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

##get-page-image## loop pages to get image files
get-page-image-UUID = $(addprefix get-page-image-, $(pages))
get-page-image: $(get-page-image-UUID)
$(get-page-image-UUID): get-page-image-%: $(IN)/periodical/$(periodical)/$(periodicalvolume)/$(periodicalitem)
	test -f $(IN)/periodical/$(periodical)/$(periodicalvolume)/$(periodicalitem)/$*.jpg \
	|| curl 'https://api.kramerius.mzk.cz/search/iiif/uuid:$*/full/max/0/default.jpg' \
	> $(IN)/periodical/$(periodical)/$(periodicalvolume)/$(periodicalitem)/$*.jpg

#
uuid2url:
	echo "TODO: not implemented $@"

######input data statistics and visualization

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

###### visualizations of intermediate data and results
##visualize-pageXML## visualize pageXML output of OCR as pdf files with original image and detected regions overlayed
visualize-pageXML: $(vizOCRxml)
	for COMP in `find $(idMapping) -type f -name "*.jsonl" -printf "%P\n" | sed 's/.jsonl$$//'| sort`;\
	do \
		echo "creating pdf: $(vizOCRxml)/$$output";\
		python Scripts/pageXML2pdf.py \
		  --images $(IN)/periodical \
			--xml $(xmlOCR)/$${COMP}/ \
			--jsonl $(idMapping)/$${COMP}.jsonl \
			--output $(vizOCRxml)/$${COMP}.pdf;\
	done

##visualize-layout-pageXML## visualize layout pageXML files
visualize-layout-pageXML: $(vizLAYOUTxml)
	for COMP in `find $(idMapping) -type f -name "*.jsonl" -printf "%P\n" | sed 's/.jsonl$$//'| sort`;\
	do \
		echo "INFO: $^/$$COMP";\
		for PAGE in `find $(xmlOCR)/$${COMP} -type f -name "*.xml" -printf "%P\n"| sed 's/.xml$$//'| sort`;\
		do \
		  python Scripts/vizRegions.py \
		    --xml $(xmlOCR)/$${COMP}/$${PAGE}.xml \
			  --output "$^/$${COMP}/$${PAGE}.png";\
			done;\
	done

##visualize-layout-alto## visualize layout ALTO files
visualize-layout-alto: $(vizLAYOUTalto) 
	for COMP in `find $(idMapping) -type f -name "*.jsonl" -printf "%P\n" | sed 's/.jsonl$$//'| sort`;\
	do \
		echo "INFO: $^/$$COMP";\
		for PAGE in `find $(altoOCR)/$${COMP} -type f -name "*.xml" -printf "%P\n"| sed 's/.xml$$//'| sort`;\
		do \
		  python Scripts/vizRegions.py \
		    --alto $(altoOCR)/$${COMP}/$${PAGE}.xml \
			  --output "$^/$${COMP}/$${PAGE}.png";\
			done;\
	done

##visualize-layout-regions## visualize layout regions detected by YOLO as png files with original image and detected regions overlayed
visualize-layout-regions: $(vizLAYOUTregions)
	echo "TODO $@"
	for COMP in `find $(imageRegions) -type f -name "*.jsonl" -printf "%P\n" | sed 's/.jsonl$$//'| sort`;\
	do \
		echo "INFO: $$COMP";\
		mkdir -p $(vizLAYOUTregions)/$$COMP;\
		rm $(vizLAYOUTregions)/$$COMP/*;\
		jq -c 'select(.image.uuid != null) | [.image.uuid, @json] | @tsv' $(imageRegions)/$$COMP.jsonl \
			| sed 's/\\t/\;/;s/^"//;s/"$$//;s/\\"/"/g' | while IFS=';' read -r uuid json; \
			do \
			  echo "$$json" >> "$(vizLAYOUTregions)/$$COMP/$${uuid}.jsonl";\
			done;\
		for PAGE in `find $(vizLAYOUTregions)/$$COMP/ -type f -name "*.jsonl" -printf "%P\n"| sed 's/.jsonl$$//'| sort`;\
		do \
		  python Scripts/vizRegions.py \
		    --jsonl $(vizLAYOUTregions)/$$COMP/$${PAGE}.jsonl \
			  --output "$^/$${COMP}/$${PAGE}.png";\
			rm $(vizLAYOUTregions)/$$COMP/$${PAGE}.jsonl;\
		done;\
	done

##visualize-layout-merge## visualize layout merge files as png files with original image and detected regions overlayed
visualize-layout-merge: $(vizLAYOUTmerge)
	for COMP in `find $(idMapping) -type f -name "*.jsonl" -printf "%P\n" | sed 's/.jsonl$$//'| sort`;\
	do \
		echo "INFO: $^/$$COMP";\
		mkdir -p $^/$$COMP;\
		jq -cr 'select(.uuid != null) | [.uuid, .uuid_path] | @tsv' "$(idMapping)/$${COMP}.jsonl" \
		  | tr "\t" ","\
			| while IFS=',' read -r UUID UUID_PATH; \
	  do\
			echo "UUID=$${UUID}";\
			echo "UUID_PATH=$${UUID_PATH}";\
			python Scripts/vizMerge.py \
		    --background $(IN)/periodical/$${UUID_PATH}.jpg \
			  --output "$^/$${COMP}/$${UUID}.jpg" \
				$(vizLAYOUTregions)/$${COMP}/$${UUID}.png \
				$(vizLAYOUTxml)/$${COMP}/$${UUID}.png \
				$(vizLAYOUTalto)/$${COMP}/$${UUID}.png;\
			done;\
	done

##visualize-tei## visualize TEI files as pdf files with original image and detected regions overlayed
visualize-tei: $(vizTEI)
	echo "TODO $@"	
	for COMP in `find $(TEI) -type f -name "*.xml" -printf "%P\n" | sed 's/.xml$$//'| sort`;\
	do \
		echo "creating pdf: $(vizTEI)/$$COMP";\
		PYTHONPATH=Scripts python -m tei2pdf.main \
		  --tei $(TEI)/$${COMP}.xml \
			--output $(vizTEI)/$${COMP}.pdf\
			--cache $(CACHE)/tei2pdf/$${COMP};\
	done

###### process metadata
##inputJsonMerge## merge issues and page json files
inputJsonMerge: $(IN)/periodical/$(UUID_PATH).json $(JSONissues)
ifeq ($(UUID_PATH_LEVEL),1)
	mkdir -p $(JSONissues)/$(UUID_PATH)
	jq -c '.response.docs[]' $< | while read -r obj; \
	do \
	  pid=$$(echo "$$obj" | jq -r '.pid'| sed "s/^uuid://") ;\
	  pages_file="$(IN)/periodical/$(UUID_PATH)/$${pid}.json" ;\
	  if [ -f "$$pages_file" ]; \
		then \
	    obj=$$(echo "$$obj" | jq --slurpfile pages "$$pages_file" '.pages = $$pages[0].response.docs') ;\
	    echo "$$obj" | jq '.' > "$(JSONissues)/$(UUID_PATH)/$${pid}.json" ;\
		  echo "INFO: saving $(JSONissues)/$(UUID_PATH)/$${pid}.json" ;\
	  fi ;\
	done
else
	@echo "ERROR: invalid UUID_PATH level - expecting volume level: periodical-uuid/volume-uuid\n"
endif

##inputJson2idMapping## create mapping of page UUIDs to page order in volume
input2outputMapping: $(IN)/periodical/$(UUID_PATH).json $(idMapping)
	$(PERL) -I Scripts/lib Scripts/idMapping.pl \
										 --input-base-dir $(JSONissues) \
										 --input-uuid-path "$(UUID_PATH)" \
										 --output-dir $(idMapping)




###### process data (img --> text --> TEI with facs and text)

$(JSONissues) $(idMapping) $(xmlOCR) $(altoOCR) $(vizOCRxml) $(vizLAYOUTxml) $(vizLAYOUTalto) $(vizLAYOUTregions) $(vizLAYOUTmerge) $(vizTEI) $(imageRegions) $(TEI) $(TEIANA) $(TEItext) $(TEItext_cleaned) $(TEIheader) $(TEIANAtext) $(UDPIPE) $(NAMETAG) $(LOGDIR) $(TEIFacsTT):
	mkdir -p $@



##inputImg2pageXML## OCR original images to pageXML
inputImg2pageXML: $(IN)/periodical/$(UUID_PATH).json $(xmlOCR) setup-pero-ocr $(PERO_OCR_MODEL_CONFIG)
	$(PERL) -I Scripts/lib Scripts/runOCR.pl \
										 --input-file-suffix ".jpg" \
										 --input-img-dir $(IN)/periodical \
										 --input-base-dir $(JSONissues) \
										 --input-uuid-path "$(UUID_PATH)" \
										 --model $(PERO_OCR_MODEL_CONFIG) \
										 --device $(PERO_OCR_DEVICE) \
										 --output-xml-dir $(xmlOCR) \
										 --output-alto-dir $(altoOCR)


##inputImg2imageRegions## detect and classify regions in original images using YOLO model
inputImg2imageRegions: $(IN)/periodical/$(UUID_PATH).json $(imageRegions) $(YOLO_MODEL)
	$(PERL) -I Scripts/lib Scripts/runImageRegionsDetection.pl \
										 --input-img-dir $(IN)/periodical \
										 --input-base-dir $(JSONissues) \
										 --input-uuid-path "$(UUID_PATH)" \
										 --model $(YOLO_MODEL) \
										 --device $(DEVICE) \
										 --output-dir $(imageRegions)

##inputJson2teiHeader## json metadata to TEI/teiHeader (expecting UUID_PATH_LEVEL>0)
inputJson2teiHeader: $(IN)/periodical/$(UUID_PATH).json $(TEIheader)
	$(PERL) -I Scripts/lib Scripts/json2teiHeader.pl \
										 --input-base-dir $(JSONissues) \
										 --input-uuid-path "$(UUID_PATH)" \
										 --output-dir $(TEIheader)

##textRegions2teiFacsText## merge region detection and ocr output to TEI documents
#### this also attempts to determine correct reading order of text regions based on pageXML reading order and detected regions, but this is not perfect and can be improved in the future
#### TODO: add some article segmentation based on detected regions and reading order, currently we just put all text regions in one big text body
textRegions2teiFacsText:
	find $(idMapping) -type f -name "*.jsonl" -printf "%P\n" | sed 's/.jsonl$$//'|sort > $(TEIFacsText).list
	cat $(TEIFacsText).list \
	  | PYTHONPATH=Scripts python -m textRegions2teiFacsText.main \
		    --ocr-xml-dir "$(xmlOCR)" \
				--regions-dir "$(imageRegions)" \
				--page-order-dir "$(idMapping)" \
				--output-dir "$(TEIFacsText)"

###### [DEPRECATED] targets

##inputTxt2teiText## [DEPRECATED] original text to TEI/text (expecting UUID_PATH_LEVEL>0)
inputTxt2teiText: $(IN)/periodical/$(UUID_PATH).json $(TEItext)
	$(PERL) -I Scripts/lib Scripts/text2teiText.pl \
										 --input-format "txt" \
										 --input-file-suffix ".txt" \
										 --input-text-dir $(IN)/periodical \
										 --input-base-dir $(JSONissues) \
										 --input-uuid-path "$(UUID_PATH)" \
										 --output-dir $(TEItext)






##teiText2teiTextCleaned## [DEPRECATED] this target should be deprecated because it removes linking between lines in text and facs
teiText2teiTextCleaned: $(TEItext_cleaned)
	find $(TEItext) -type f -name "*.xml"  -printf "%P\n" | xargs -I {} $(SAXON) outFile=$</{} -xsl:Scripts/remove-lb.xsl $(TEItext)/{}

# [DEPRECATED]
### annotate TEI/text
##teiText2teiTextAnaUD## [DEPRECATED] annotate TEI/text with UDPipe (lemmatization, POS tagging, dependency parsing)
teiText2teiTextAnaUD: $(UDPIPE)
	find $(TEItext_cleaned) -type f -printf "%P\n" |sort > $(UDPIPE).fl
	$(PERL) -I Scripts/resources/lib Scripts/resources/udpipe2/udpipe2.pl --colon2underscore \
	                               $(TOKEN) \
	                               --model "cs:czech-pdtc-ud-2.17-251125" \
	                               --elements "p,head" \
	                               --debug \
																 --use-xpos \
	                               --no-space-in-punct \
	                               --try2continue-on-error \
	                               --filelist $(UDPIPE).fl \
	                               --input-dir $(TEItext_cleaned) \
	                               --output-dir $(UDPIPE)
# [DEPRECATED]
##teiText2teiTextAnaNER## [DEPRECATED] annotate TEI/text with NameTag (named entity recognition)
teiText2teiTextAnaNER: $(NAMETAG)
	find $(UDPIPE) -type f -printf "%P\n" |sort > $(NAMETAG).fl
	$(PERL) -I Scripts/resources/lib Scripts/resources/nametag2/nametag2.pl \
	                                 $(TOKEN) \
																	 --debug \
	                                 --model "cs:nametag3-czech-cnec2.0-240830" \
																	 --cnec2conll2003 \
	                                 --filelist $(NAMETAG).fl \
	                                 --input-dir $(UDPIPE) \
	                                 --output-dir $(NAMETAG)
###### Linguistic annotation of TEI documents
##teiText2tt## annotate teiFacsText with flexipipe TEIFacsTT
teiText2tt: $(TEIFacsTT)
	find $(TEIFacsText) -type f -name "*.xml"  -printf "%P\n"| sort > $(TEIFacsTT).fl
	cat $(TEIFacsTT).fl | sed 's@/.*@@'|sort|uniq | xargs -I {} mkdir -p $(TEIFacsTT)/{}
	cat $(TEIFacsTT).fl | xargs -I {} cp $(TEIFacsText)/{} $(TEIFacsTT)/{}
	#cat $(TEIFacsTT).fl | xargs -I {} \
	#  xmlstarlet edit --inplace \
	#	--delete "//_:pc[@force='weak']" \
	#	--delete "//_:lb[@break='no']" \
	#	$(TEIFacsTT)/{}
	cat $(TEIFacsTT).fl | xargs -I {} \
	  $(FLEXIPIPE) \
	  process --verbose --debug --teitok \
		--input $(TEIFacsTT)/{} \
		--tokenize --backend udpipe --ner-backend nametag --language cs \
		--model czech-pdtc-ud-2.17-251125 \
		--nametag-model nametag3-multilingual-conll-250203 \
		--tasks segment,tokenize,lemmatize,tag,ner \
		--writeback

##TT2teiANA## convert TEIFacsTT to TEIANAtext
TT2teiANA: $(TEIANAtext)
	find $(TEIFacsTT) -type f -name "*.xml" -printf "%P\n" |sort > $(TEIANAtext).fl
	cat $(TEIFacsTT).fl | sed 's@/.*@@'|sort|uniq | xargs -I {} mkdir -p $(TEIANAtext)/{}
	cat $(TEIFacsTT).fl | xargs -I {} \
	  python Scripts/teitok2tei.py \
			--input $(TEIFacsTT)/{} \
			--output $(TEIANAtext)/{} 


###### Build TEI documents and corpus

##corpus-template## create TEI corpus template with xi:include for all TEI headers and text components, this is used as input for distribution XSLT stylesheet to create final TEI documents with included headers and text
corpus-template:
	echo '<?xml version="1.0" encoding="UTF-8"?>' > $(CORPUS_TEMPLATE)
	echo '<teiCorpus xmlns="http://www.tei-c.org/ns/1.0"' >> $(CORPUS_TEMPLATE)
	echo '     xml:id="PressMint-CZ"' >> $(CORPUS_TEMPLATE)
	echo '     xml:lang="cs">' >> $(CORPUS_TEMPLATE)
	find $(TEIheader) -type f -name "*.xml" -printf "%P\n"| xargs -I {} echo '  <xi:include xmlns:xi="http://www.w3.org/2001/XInclude" href="'{}'"/>' >> $(CORPUS_TEMPLATE)
	echo '</teiCorpus>' >> $(CORPUS_TEMPLATE)

##dist-tei## create final TEI documents with included headers and text
dist-tei: $(TEI)
	$(SAXON) -xsl:Scripts/distro.xsl \
	    outDir=$< \
	    inComponentDir=$(TEIFacsText) \
	    inHeaderDir=$(TEIheader) \
	    anaDir=$(TEIANA) \
	    inTaxonomiesDir=$(TAXONOMIES) \
	    type=TEI \
	    projectConfig=$(CONFIG) \
	    $(CORPUS_TEMPLATE)

##dist-tei-ana## create final TEI documents with included headers and text
dist-tei-ana: $(TEIANA)
	$(SAXON) -xsl:Scripts/distro.xsl \
	    outDir=$< \
	    inComponentDir=$(TEIANAtext) \
	    inHeaderDir=$(TEIheader) \
	    inTaxonomiesDir=$(TAXONOMIES) \
	    type=TEI.ana \
	    projectConfig=$(CONFIG) \
	    $(CORPUS_TEMPLATE)


######setup and resources
####
prereq: parczech

parczech: Scripts/resources
	git clone https://github.com/ufal/ParCzech.git --no-checkout $</ParCzech --depth 10 -b master ;\
	cd $</ParCzech ;\
	git sparse-checkout init --cone  ;\
	git sparse-checkout set src/udpipe2 src/nametag2 src/lib || echo "directory exists"
	ln -s ParCzech/src/lib $</lib || : 
	ln -s ParCzech/src/udpipe2 $</udpipe2 || :
	ln -s ParCzech/src/nametag2 $</nametag2 || :
	### 
	cd $</ParCzech ;\
  git checkout ;\
  git pull

Scripts/resources:
	mkdir $@

setup-python: $(VENV_DIR)
	. $(VENV_DIR)/bin/activate;\
	pip install -r Scripts/requirements.txt

$(VENV_DIR):
	python3 -m venv $(VENV_DIR)
	. $(VENV_DIR)/bin/activate

setup-pero-ocr: setup-python $(PERO_OCR_STAMP)

$(PERO_OCR_STAMP):
	. $(VENV_DIR)/bin/activate;\
	pip install git+https://github.com/DCGM/pero-ocr.git@$(PERO_OCR_COMMIT)
	touch $@


$(PERO_OCR_MODEL_CONFIG):
	cd Models;\
	wget $(PERO_OCR_MODEL_URL) -O $(PERO_OCR_MODEL_NAME).$(PERO_OCR_MODEL_ARCHEXT);\
	unzip $(PERO_OCR_MODEL_NAME).$(PERO_OCR_MODEL_ARCHEXT)


###### Help

help-intro:
	@echo "Pipeline of PressMint-CZ data processing:\n\t \n "
	@echo "Process data directories:\n\t./Sample when SAMPLE=1 variable is set\n\t./Data (default)\n\t$(DATA) (currently set)"
	@echo "Directories structure:\n\t$(IN)\n\t$(WORK)\n\t$(VIZ)\n\t$(DIST)"

help-variables:
	@echo "\033[1m\033[32mVARIABLES:\033[0m"
	@echo "Variable VAR with value 'value' can be set when calling target TARGET in $(MAKEFILE_LIST): make VAR=value TARGET\n"
	@awk '/^##\$$[a-zA-Z0-9_-]+/ { \
		comment = $$0; \
		getline; \
		split(comment, comment_parts, "##\\$$|##"); \
		var_name = comment_parts[2]; \
		desc = comment_parts[3]; \
		print var_name " " desc; \
	}' $(MAKEFILE_LIST) | while read -r var_name desc; do \
		eval current_val="\"\$$$${var_name}\""; \
		printf "\033[36m%-20s\033[0m %s \n\t=\033[1;33m%s \033[0m(current)\n" "$$var_name" "$$desc" "$$current_val"; \
	done


help-targets:
	@echo "\033[1m\033[32mTARGETS:\033[0m"
	@grep -E '^## *[a-zA-Z_-]+.*?##.*$$|^####' $(MAKEFILE_LIST) | awk 'BEGIN {FS = " *## *"}; {printf "\033[1m%s\033[0m\033[36m%-25s\033[0m %s\n", $$4, $$2, $$3}'


.PHONY: help
## help ## print this help
help: help-intro help-variables help-targets