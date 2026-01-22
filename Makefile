.DEFAULT_GOAL := help

VENV_DIR=env
export PATH := $(abspath $(VENV_DIR)/bin):$(PATH)

-include .env
export

DEVICE = cpu

PERO_OCR_COMMIT := b5ced044e7f6e44f34b257ed75a527f01f91b482
PERO_OCR_STAMP = $(VENV_DIR)/.pero-ocr-$(PERO_OCR_COMMIT)

PERO_OCR_DEVICE := $(DEVICE)
PERO_OCR_MODEL_URL := https://nextcloud.fit.vutbr.cz/public.php/dav/files/NtAbHTNkZFpapdJ
PERO_OCR_MODEL_NAME := pero_eu_cz_print_newspapers_2022-09-26
PERO_OCR_MODEL_ARCHEXT := zip
PERO_OCR_MODEL_CONFIG := Models/$(PERO_OCR_MODEL_NAME)/config_cpu.ini

YOLO_MODEL := Models/textbite/yolo-m-1200.pt


PERLBREW_ROOT=~/perl5/perlbrew
PERL := $(shell test -n "$(USE_PERL)" && echo -n "$(PERLBREW_ROOT)/perls/$(USE_PERL)/bin/perl" || echo -n "perl")

SAMPLE ?= 0
DATA ?= $(shell pwd)/Data/
SAMPLE_SOURCE_SOURCE = $(shell pwd)/Data/source
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
TEIheader := ${WORK}/tei-header
OCR := ${WORK}/OCR
vizOCR := ${VIZ}/ocr
vizOCRpageXMLpdf := $(vizOCR)/pageXMLpdf
vizLAYOUT := ${VIZ}/layout
vizLAYOUTxml := $(vizLAYOUT)/xml
vizLAYOUTalto := $(vizLAYOUT)/alto
vizLAYOUTregions := $(vizLAYOUT)/regions
vizLAYOUTmerge := $(vizLAYOUT)/merged

imageRegions := ${WORK}/imageRegions
readingOrder := ${WORK}/readingOrder
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



### process data

$(JSONissues) $(OCR) $(vizOCRpageXMLpdf) $(vizLAYOUTxml) $(vizLAYOUTalto) $(vizLAYOUTregions) $(vizLAYOUTmerge) $(imageRegions) $(TEI) $(TEIANA) $(TEItext) $(TEItext_cleaned) $(TEIheader) $(TEIANAtext) $(UDPIPE) $(NAMETAG) $(LOGDIR):
	mkdir -p $@
# merge issues and page json files

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


# original images to pageXML

inputImg2pageXML: $(IN)/periodical/$(UUID_PATH).json $(OCR) setup-pero-ocr $(PERO_OCR_MODEL_CONFIG)
	$(PERL) -I Scripts/lib Scripts/runOCR.pl \
										 --input-file-suffix ".jpg" \
										 --input-img-dir $(IN)/periodical \
										 --input-base-dir $(JSONissues) \
										 --input-uuid-path "$(UUID_PATH)" \
										 --model $(PERO_OCR_MODEL_CONFIG) \
										 --device $(PERO_OCR_DEVICE) \
										 --output-dir $(OCR)

visualize-pageXML: $(vizOCR)
	find $(OCR) -type f -name "pages.tsv" -printf "%P\n" |sort > $(vizOCR).fl
	for TSV in `cat $(vizOCR).fl`;\
	do \
		output=`echo $$TSV| sed "s/\/pages.tsv/.pdf/"`;\
		echo "creating pdf: $(vizOCR)/$$output";\
		python Scripts/pageXML2pdf.py \
		  --images $(IN)/periodical \
			--xml $$(dirname $(OCR)/$${TSV})/XML/ \
			--tsv $(OCR)/$${TSV} \
			--output $(vizOCR)/$$output;\
	done

visualize-layout-pageXML: $(vizLAYOUTxml)
	for COMP in `find $(OCR) -type f -name "pages.tsv" -printf "%P\n" | sed 's/\/pages.tsv$$//'| sort`;\
	do \
		echo "INFO: $^/$$COMP";\
		for PAGE in `find $(OCR)/$${COMP}/XML -type f -name "*.xml" -printf "%P\n"| sed 's/.xml$$//'| sort`;\
		do \
		  python Scripts/vizRegions.py \
		    --xml $(OCR)/$${COMP}/XML/$${PAGE}.xml \
			  --output "$^/$${COMP}/$${PAGE}.png";\
			done;\
	done


visualize-layout-alto: $(vizLAYOUTalto) 
	for COMP in `find $(OCR) -type f -name "pages.tsv" -printf "%P\n" | sed 's/\/pages.tsv$$//'| sort`;\
	do \
		echo "INFO: $^/$$COMP";\
		for PAGE in `find $(OCR)/$${COMP}/ALTO -type f -name "*.xml" -printf "%P\n"| sed 's/.xml$$//'| sort`;\
		do \
		  python Scripts/vizRegions.py \
		    --alto $(OCR)/$${COMP}/ALTO/$${PAGE}.xml \
			  --output "$^/$${COMP}/$${PAGE}.png";\
			done;\
	done


visualize-layout-regions: $(vizLAYOUTregions)
	echo "TODO $@"


visualize-layout-merge: $(vizLAYOUTmerge)
	for COMP in `find $(OCR) -type f -name "pages.tsv" -printf "%P\n" | sed 's/\/pages.tsv$$//'| sort`;\
	do \
		echo "INFO: $^/$$COMP";\
		mkdir -p $^/$$COMP;\
		echo "$(OCR)/$${COMP}/pages.tsv";\
		echo "=============";\
		tail -n +2 "$(OCR)/$${COMP}/pages.tsv"| tr "\t" "," | while IFS=',' read -r n UUID UUID_PATH teiid url; \
	  do\
			echo "UUID=$${UUID}";\
			echo "UUID_PATH=$${UUID_PATH}";\
			python Scripts/vizMerge.py \
		    --background $(IN)/periodical/$${UUID_PATH}.jpg \
			  --output "$^/$${COMP}/$${UUID}.jpg" \
				$(vizLAYOUTxml)/$${COMP}/$${UUID}.png \
				$(vizLAYOUTalto)/$${COMP}/$${UUID}.png;\
			done;\
	done


inputImg2imageRegions: $(IN)/periodical/$(UUID_PATH).json $(imageRegions) $(YOLO_MODEL)
	$(PERL) -I Scripts/lib Scripts/runImageRegionsDetection.pl \
										 --input-img-dir $(IN)/periodical \
										 --input-base-dir $(JSONissues) \
										 --input-uuid-path "$(UUID_PATH)" \
										 --model $(YOLO_MODEL) \
										 --device $(DEVICE) \
										 --output-dir $(imageRegions)


# merge region detection and ocr output
readingOrder:
	find $(OCR) -type f -name "pages.tsv" -printf "%P\n" | sed 's/\/pages.tsv$$//'|sort > $(readingOrder).list
	cat $(readingOrder).list \
	  | python Scripts/readingOrder.py \
		    --ocr-dir "$(OCR)" \
				--ocr-xml-dir "XML" \
				--regions-dir "$(imageRegions)" \
				--output-dir "$(readingOrder)"

# [DEPRECATED] original text to TEI/text (expecting UUID_PATH_LEVEL>0)
inputTxt2teiText: $(IN)/periodical/$(UUID_PATH).json $(TEItext)
	$(PERL) -I Scripts/lib Scripts/text2teiText.pl \
										 --input-format "txt" \
										 --input-file-suffix ".txt" \
										 --input-text-dir $(IN)/periodical \
										 --input-base-dir $(JSONissues) \
										 --input-uuid-path "$(UUID_PATH)" \
										 --output-dir $(TEItext)



# json metadata to TEI/teiHeader (expecting UUID_PATH_LEVEL>0)
inputJson2teiHeader: $(IN)/periodical/$(UUID_PATH).json $(TEIheader)
	$(PERL) -I Scripts/lib Scripts/json2teiHeader.pl \
										 --input-base-dir $(JSONissues) \
										 --input-uuid-path "$(UUID_PATH)" \
										 --output-dir $(TEIheader)


teiText2teiTextCleaned: $(TEItext_cleaned)
	find $(TEItext) -type f -name "*.xml"  -printf "%P\n" | xargs -I {} $(SAXON) outFile=$</{} -xsl:Scripts/remove-lb.xsl $(TEItext)/{}


### annotate TEI/text
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


### merge data to TEI and teiCorpus


corpus-template:
	echo '<?xml version="1.0" encoding="UTF-8"?>' > $(CORPUS_TEMPLATE)
	echo '<teiCorpus xmlns="http://www.tei-c.org/ns/1.0"' >> $(CORPUS_TEMPLATE)
	echo '     xml:id="PressMint-CZ"' >> $(CORPUS_TEMPLATE)
	echo '     xml:lang="cs">' >> $(CORPUS_TEMPLATE)
	find $(TEIheader) -type f -name "*.xml" -printf "%P\n"| xargs -I {} echo '  <xi:include xmlns:xi="http://www.w3.org/2001/XInclude" href="'{}'"/>' >> $(CORPUS_TEMPLATE)
	echo '</teiCorpus>' >> $(CORPUS_TEMPLATE)

dist-tei: $(TEI)
	$(SAXON) -xsl:Scripts/distro.xsl \
	    outDir=$< \
	    inComponentDir=$(TEItext) \
	    inHeaderDir=$(TEIheader) \
	    anaDir=$(TEIANA) \
	    inTaxonomiesDir=$(TAXONOMIES) \
	    type=TEI \
	    projectConfig=$(CONFIG) \
	    $(CORPUS_TEMPLATE)

dist-tei-ana: $(TEIANA)
	$(SAXON) -xsl:Scripts/distro.xsl \
	    outDir=$< \
	    inComponentDir=$(NAMETAG) \
	    inHeaderDir=$(TEIheader) \
	    inTaxonomiesDir=$(TAXONOMIES) \
	    type=TEI.ana \
	    projectConfig=$(CONFIG) \
	    $(CORPUS_TEMPLATE)

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