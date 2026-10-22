<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet version="3.0"
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:xi="http://www.w3.org/2001/XInclude"
  xmlns:xs="http://www.w3.org/2001/XMLSchema"
  xmlns:map="http://www.w3.org/2005/xpath-functions/map"
  xmlns:err="http://www.w3.org/2005/xqt-errors"
  xmlns:tei="http://www.tei-c.org/ns/1.0"
  xmlns="http://www.tei-c.org/ns/1.0"
  xmlns:mk="http://ufal.mff.cuni.cz/matyas-kopp"
  exclude-result-prefixes="xs map err tei xi mk">

  <!-- Components are processed one at a time (xsl:iterate) and read with xsl:source-document,
       which (unlike document()) does not keep the documents in Saxon's document pool.
       Only aggregated values (word count, tag usages) are passed to the root file. -->

  <xsl:output method="xml" indent="yes" encoding="UTF-8" suppress-indentation="w pc"/>

  <xsl:param name="outDir" />
  <xsl:param name="inComponentDir" />
  <xsl:param name="inFacsDir" />
  <xsl:param name="inHeaderDir" />
  <xsl:param name="anaDir" />
  <xsl:param name="inTaxonomiesDir" />
  <xsl:param name="type" /> <!-- TEI or TEI.ana-->
  <xsl:param name="projectConfig" />

  <xsl:preserve-space elements="catDesc seg p" />

  <xsl:variable name="config">
    <xsl:message>READING CONFIG <xsl:value-of select="$projectConfig" /></xsl:message>
    <xsl:copy-of
      select="document($projectConfig)/tei:config/*" />
  </xsl:variable>

  <xsl:variable name="outRoot">
    <xsl:value-of select="$outDir" />
    <xsl:text>/</xsl:text>
    <xsl:value-of
      select="replace(base-uri(), '.*/(.+).xml$', '$1')" />
    <xsl:choose>
      <xsl:when test="$type = 'TEI.ana'">.ana.xml</xsl:when>
      <xsl:when test="$type = 'TEI'">.xml</xsl:when>
      <xsl:otherwise>
        <xsl:message terminate="yes">invalid type param: allowed values are 'TEI' and 'TEI.ana'</xsl:message>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:variable name="suff">
    <xsl:choose>
      <xsl:when test="$type = 'TEI.ana'">.ana</xsl:when>
      <xsl:otherwise><text /></xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <xsl:template match="/">
    <xsl:message select="concat('INFO: Starting to process ', tei:teiCorpus/@xml:id)" />
    <xsl:variable name="corpusDoc" select="." />
    <xsl:iterate select="/tei:teiCorpus/xi:include">
      <xsl:param name="wordsTotal" as="xs:integer" select="0" />
      <xsl:param name="tagTotals" as="map(xs:string, xs:integer)" select="map{}" />
      <xsl:param name="okHrefs" as="map(xs:string, xs:boolean)" select="map{}" />

      <!-- Output Root file -->
      <xsl:on-completion>
        <xsl:variable name="skipped" select="count($corpusDoc/tei:teiCorpus/xi:include) - map:size($okHrefs)" />
        <xsl:if test="$skipped > 0">
          <xsl:message select="concat('ERROR: ', $skipped, ' component(s) skipped because of missing or broken input files')" />
        </xsl:if>
        <xsl:message>INFO: processing root </xsl:message>
        <xsl:result-document href="{$outRoot}">
          <xsl:variable name="corpus">
            <xsl:apply-templates select="$corpusDoc" mode="insertHeader">
              <xsl:with-param name="fileType">root</xsl:with-param>
            </xsl:apply-templates>
          </xsl:variable>
          <xsl:apply-templates mode="root" select="$corpus">
            <xsl:with-param name="wordsTotal" select="$wordsTotal" tunnel="yes" />
            <xsl:with-param name="okHrefs" select="$okHrefs" tunnel="yes" />
            <xsl:with-param name="tagUsages" tunnel="yes">
              <xsl:for-each select="map:keys($tagTotals)">
                <xsl:sort select="." />
                <tagUsage gi="{.}" occurs="{$tagTotals(.)}" />
              </xsl:for-each>
            </xsl:with-param>
          </xsl:apply-templates>
        </xsl:result-document>
      </xsl:on-completion>

      <!-- Process component file -->
      <xsl:variable name="this" select="string(@href)" />
      <xsl:message select="concat('INFO: Processing ', $this)" />
      <xsl:variable name="xi-new" select="if ($type = 'TEI.ana') then mk:ana-href($this) else $this" />

      <!-- Load input files; a missing, empty or unparsable file is reported and the component is skipped -->
      <xsl:variable name="url-header" select="concat($inHeaderDir, '/', $this)" />
      <xsl:variable name="teiHeader" as="element()?">
        <xsl:try>
          <xsl:source-document href="{$url-header}" streamable="no">
            <xsl:copy-of select="tei:TEI/tei:teiHeader" />
            <xsl:if test="not(tei:TEI/tei:teiHeader)">
              <xsl:message select="concat('ERROR ', $this, ': missing TEI/teiHeader in header file ', $url-header)" />
            </xsl:if>
          </xsl:source-document>
          <xsl:catch>
            <xsl:message select="concat('ERROR ', $this, ': cannot read header file ', $url-header, ': ', $err:description)" />
          </xsl:catch>
        </xsl:try>
      </xsl:variable>
      <xsl:variable name="url-facs" select="concat($inFacsDir, '/', $this)" />
      <xsl:variable name="facsimile" as="element()?">
        <xsl:try>
          <xsl:source-document href="{$url-facs}" streamable="no">
            <xsl:copy-of select="tei:TEI/tei:facsimile" />
            <xsl:if test="not(tei:TEI/tei:facsimile)">
              <xsl:message select="concat('ERROR ', $this, ': missing TEI/facsimile in facs file ', $url-facs)" />
            </xsl:if>
          </xsl:source-document>
          <xsl:catch>
            <xsl:message select="concat('ERROR ', $this, ': cannot read facs file ', $url-facs, ': ', $err:description)" />
          </xsl:catch>
        </xsl:try>
      </xsl:variable>
      <!-- For plain files, number of words is taken from the .ana file, which is required -->
      <xsl:variable name="url-ana" select="concat($anaDir, '/', mk:ana-href($this))" />
      <xsl:variable name="anaWords" as="xs:integer?">
        <xsl:if test="$type = 'TEI' and $teiHeader and $facsimile">
          <xsl:try>
            <xsl:source-document href="{$url-ana}" streamable="no">
              <xsl:variable name="quantity"
                select="(tei:TEI/tei:teiHeader//tei:extent/tei:measure[@unit='words'])[1]/@quantity" />
              <xsl:choose>
                <xsl:when test="$quantity castable as xs:integer">
                  <xsl:sequence select="xs:integer($quantity)" />
                </xsl:when>
                <xsl:otherwise>
                  <xsl:message select="concat('ERROR ', $this, ': missing number of words in .ana file ', $url-ana)" />
                </xsl:otherwise>
              </xsl:choose>
            </xsl:source-document>
            <xsl:catch>
              <xsl:message select="concat('ERROR ', $this, ': cannot read .ana file ', $url-ana, ': ', $err:description)" />
            </xsl:catch>
          </xsl:try>
        </xsl:if>
      </xsl:variable>
      <xsl:variable name="url-text" select="concat($inComponentDir, '/', $this)" />
      <xsl:variable name="doc" as="document-node()?">
        <xsl:if test="$teiHeader and $facsimile and ($type = 'TEI.ana' or exists($anaWords))">
          <xsl:try>
            <xsl:source-document href="{$url-text}" streamable="no">
              <xsl:choose>
                <xsl:when test="tei:TEI">
                  <xsl:variable name="docWithHeader">
                    <xsl:apply-templates select="." mode="insertHeader">
                      <xsl:with-param name="teiHeader" select="$teiHeader" />
                      <xsl:with-param name="facsimile" select="$facsimile" />
                      <xsl:with-param name="fileType">comp</xsl:with-param>
                    </xsl:apply-templates>
                  </xsl:variable>
                  <xsl:document>
                    <xsl:apply-templates mode="compCleanup" select="$docWithHeader" />
                  </xsl:document>
                </xsl:when>
                <xsl:otherwise>
                  <xsl:message select="concat('ERROR ', $this, ': missing TEI in text file ', $url-text)" />
                </xsl:otherwise>
              </xsl:choose>
            </xsl:source-document>
            <xsl:catch>
              <xsl:message select="concat('ERROR ', $this, ': cannot read text file ', $url-text, ': ', $err:description)" />
            </xsl:catch>
          </xsl:try>
        </xsl:if>
      </xsl:variable>

      <xsl:choose>
        <xsl:when test="empty($doc)">
          <xsl:message select="concat('ERROR ', $this, ': skipping component')" />
          <xsl:next-iteration>
            <xsl:with-param name="wordsTotal" select="$wordsTotal" />
            <xsl:with-param name="tagTotals" select="$tagTotals" />
            <xsl:with-param name="okHrefs" select="$okHrefs" />
          </xsl:next-iteration>
        </xsl:when>
        <xsl:otherwise>
          <!-- Number of words: computed for .ana files, taken from .ana files for plain files -->
          <xsl:variable name="words" as="xs:integer"
            select="if ($type = 'TEI.ana') then count($doc//tei:w[not(parent::tei:w)]) else $anaWords" />

          <!-- tagUsages in component file -->
          <xsl:variable name="tagUsages">
            <item>
              <xsl:for-each-group select="$doc/tei:TEI/tei:text/descendant-or-self::tei:*" group-by="name()">
                <xsl:sort select="current-grouping-key()" />
                <tagUsage gi="{current-grouping-key()}" occurs="{count(current-group())}" />
              </xsl:for-each-group>
            </item>
          </xsl:variable>

          <xsl:result-document href="{concat($outDir, '/', $xi-new)}">
            <xsl:apply-templates mode="comp" select="$doc/tei:TEI">
              <xsl:with-param name="words" select="$words" />
              <xsl:with-param name="tagUsages" select="$tagUsages/tei:item" />
              <xsl:with-param name="date" select="$doc/tei:TEI/tei:teiHeader//tei:sourceDesc/tei:bibl/tei:date/@when/string()" />
              <xsl:with-param name="title" select="normalize-space($doc/tei:TEI/tei:teiHeader//tei:sourceDesc/tei:bibl/tei:title/text())" />
            </xsl:apply-templates>
          </xsl:result-document>
          <xsl:message select="concat('INFO: Saving to ', $xi-new)" />

          <xsl:next-iteration>
            <xsl:with-param name="wordsTotal" select="$wordsTotal + $words" />
            <xsl:with-param name="tagTotals"
              select="fold-left($tagUsages/tei:item/tei:tagUsage, $tagTotals,
                        function($m, $t) {
                          map:put($m, string($t/@gi), ($m(string($t/@gi)), 0)[1] + xs:integer($t/@occurs))
                        })" />
            <xsl:with-param name="okHrefs" select="map:put($okHrefs, $this, true())" />
          </xsl:next-iteration>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:iterate>
  </xsl:template>

  <!-- root -->
  <xsl:template mode="root" match="*">
    <xsl:copy>
      <xsl:apply-templates mode="root" select="@*" />
      <xsl:apply-templates mode="root"/>
    </xsl:copy>
  </xsl:template> 

  <xsl:template mode="root" match="tei:TITLE_PLACEHOLDER"/>

  <xsl:template mode="root" match="tei:teiCorpus/@xml:id">
    <xsl:attribute name="xml:id">
      <xsl:value-of select="concat(.,$suff)" />
    </xsl:attribute>
  </xsl:template>

  <xsl:template mode="root" match="@*">
    <xsl:copy />
  </xsl:template>

  <xsl:template mode="root" match="tei:extent">
    <xsl:param name="wordsTotal" tunnel="yes" />
    <xsl:copy>
      <xsl:call-template name="add-measure-words">
        <xsl:with-param name="quantity" select="$wordsTotal" />
      </xsl:call-template>
    </xsl:copy>
  </xsl:template>

  <xsl:template mode="root" match="xi:include[parent::tei:classDecl]">
    <xsl:variable name="taxonomy" select="document(concat($inTaxonomiesDir, '/', @href))"/>
    <xsl:copy>
      <xsl:apply-templates select="@*" mode="root"/>
    </xsl:copy>
    <xsl:variable name="outTaxonomy" select="concat($outDir,'/',@href)"/>
    <xsl:result-document href="{$outTaxonomy}">
      <xsl:copy-of select="$taxonomy"/>
    </xsl:result-document>
  </xsl:template>

  <xsl:template mode="root" match="tei:teiCorpus">
    <xsl:param name="okHrefs" tunnel="yes" />
    <xsl:copy>
      <xsl:apply-templates select="@*" mode="root"/>
      <xsl:apply-templates select="tei:*" mode="root"/>
      <!-- include only successfully processed components -->
      <xsl:for-each select="xi:include[map:contains($okHrefs, string(@href))]">
        <xsl:sort select="@href"/>
        <xsl:variable name="href" select="@href"/>
        <xsl:variable name="new-href" select="if ($type = 'TEI.ana') then mk:ana-href($href) else string($href)"/>
        <xsl:message select="concat('INFO: Fixing xi:include: ',$href,' ',$new-href)"/>
        <xsl:copy>
          <xsl:attribute name="href" select="$new-href"/>
        </xsl:copy>
      </xsl:for-each>
    </xsl:copy>
  </xsl:template>


  <xsl:template mode="root" match="tei:tagsDecl">
    <xsl:param name="tagUsages" tunnel="yes" />
    <xsl:call-template name="add-tagsDecl">
      <xsl:with-param name="tagUsages" select="$tagUsages" />
    </xsl:call-template>
  </xsl:template>

  <!-- REMOVE CONTENT from comp-->
  <xsl:template mode="compCleanup" match="tei:linkGrp[parent::tei:s]"/> <!-- removing syntax -->
  <xsl:template mode="compCleanup" match="@ana[parent::tei:w or parent::tei:pc]"/> <!-- pdt tagset -->
  <!-- removing cnec: -->
  <xsl:template mode="compCleanup" match="tei:name[@type]">
    <xsl:copy>
      <xsl:apply-templates mode="compCleanup" select="@*[local-name() != 'ana']"/>
      <xsl:apply-templates mode="compCleanup"/>
    </xsl:copy>
  </xsl:template>
  <xsl:template mode="compCleanup" match="tei:name[not(@type) and @ana] | tei:date[@ana] | tei:email[@ana] | tei:num[@ana] | tei:ref[@ana] | tei:time[@ana] | tei:unit[@ana] ">
    <xsl:apply-templates mode="compCleanup"/>
  </xsl:template>
  <xsl:template mode="compCleanup" match="*">
    <xsl:copy>
      <xsl:apply-templates mode="compCleanup" select="@*" />
      <xsl:apply-templates mode="compCleanup"/>
    </xsl:copy>
  </xsl:template>
  <xsl:template mode="compCleanup" match="@*">
    <xsl:copy />
  </xsl:template>
  <xsl:template match="comment()"  mode="compCleanup">
    <xsl:copy/>
  </xsl:template>
  <!-- component -->

  <xsl:template mode="comp" match="*">
    <xsl:param name="words" />
    <xsl:param name="tagUsages" />
    <xsl:param name="date" />
    <xsl:param name="title" />
    <xsl:copy>
      <xsl:apply-templates mode="comp" select="@*" />
      <xsl:apply-templates mode="comp">
        <xsl:with-param name="words" select="$words" />
        <xsl:with-param name="tagUsages" select="$tagUsages" />
        <xsl:with-param name="date" select="$date" />
        <xsl:with-param name="title" select="$title" />
      </xsl:apply-templates>
    </xsl:copy>
  </xsl:template>

  <xsl:template mode="comp" match="tei:TITLE_PLACEHOLDER">
    <xsl:param name="words" />
    <xsl:param name="tagUsages" />
    <xsl:param name="date" />
    <xsl:param name="title" />
    <xsl:text>, </xsl:text>
    <xsl:value-of select="$title"/>
    <xsl:text>, </xsl:text>
    <xsl:value-of select="$date"/>
  </xsl:template>

  <xsl:template mode="comp" match="@*">
    <xsl:copy />
  </xsl:template>

  <xsl:template mode="comp" match="tei:TEI/@xml:id">
    <xsl:attribute name="xml:id">
      <xsl:value-of select="concat(.,$suff)" />
    </xsl:attribute>
  </xsl:template>

  <xsl:template mode="comp" match="text()[normalize-space(.)]">
    <xsl:variable name="str" select="replace(., '\s+', ' ')" />
    <xsl:choose>
      <xsl:when test="(not(preceding-sibling::tei:*) and matches($str, '^ ')) and
                      (not(following-sibling::tei:*) and matches($str, ' $'))">
        <xsl:value-of select="replace($str, '^ (.+?) $', '$1')" />
      </xsl:when>
      <xsl:when test="not(preceding-sibling::tei:*) and matches($str, '^ ')">
        <xsl:value-of select="replace($str, '^ ', '')" />
      </xsl:when>
      <xsl:when test="not(following-sibling::tei:*) and matches($str, ' $')">
        <xsl:value-of select="replace($str, ' $', '')" />
      </xsl:when>
      <xsl:otherwise>
        <xsl:value-of select="$str" />
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <xsl:template mode="comp" match="tei:extent">
    <xsl:param name="words" />
    <xsl:copy>
      <xsl:call-template name="add-measure-words">
        <xsl:with-param name="quantity" select="$words" />
      </xsl:call-template>
    </xsl:copy>
  </xsl:template>

  <xsl:template mode="comp" match="tei:tagsDecl">
    <xsl:param name="tagUsages" />
    <xsl:call-template name="add-tagsDecl">
      <xsl:with-param name="tagUsages" select="$tagUsages" />
    </xsl:call-template>
  </xsl:template>

  <xsl:template match="comment()"  mode="comp">
    <xsl:copy/>
  </xsl:template>

  <!-- merge header and text content -->
  <xsl:template mode="insertHeader" match="tei:TEI | tei:teiCorpus">
    <xsl:param name="teiHeader" />
    <xsl:param name="facsimile" />    
    <xsl:copy>
      <xsl:copy-of select="@*" />
      <!-- <xsl:apply-templates select="$teiHeader" mode="insertHeader"/> předělat na volání
      templaty a doplnit extent,...-->
      <teiHeader>
        <xsl:apply-templates select="$config/tei:teiHeader/*" mode="insertConfig">
          <xsl:with-param name="elem" select="$teiHeader" />
          <xsl:with-param name="fileType">
            <xsl:choose>
              <xsl:when test="local-name() = 'TEI'">comp</xsl:when>
              <xsl:otherwise>root</xsl:otherwise>
            </xsl:choose>
          </xsl:with-param>
        </xsl:apply-templates>
      </teiHeader>
      <xsl:copy-of select="$facsimile"/>
      <xsl:copy-of select="./*" />
    </xsl:copy>
  </xsl:template>
  
  <xsl:template match="tei:*|xi:include" mode="insertConfig">
    <xsl:param name="elem"/>
    <xsl:param name="fileType"/>
    <xsl:variable name="name" select="local-name()" />
    <xsl:choose>
      <xsl:when test="@condition
                      and
                      not(
                        $type = @condition
                        or $fileType = @condition
                        or concat($fileType,'.',$type) = @condition
                        )">
        <!-- does not meet the condition -->
      </xsl:when>
      <xsl:when test="$elem and $elem/*[local-name() = $name]">
        <xsl:choose>
          <xsl:when test="@placeholder"> <!-- config contains only placeholder -->
            <xsl:copy-of select="$elem/*[local-name() = $name]" />
          </xsl:when>
          <xsl:when test="count($elem/*[local-name() = $name]) = 1">
            <xsl:copy>
              <xsl:apply-templates select="@*" mode="insertConfig" />
              <xsl:apply-templates
                select="$elem/*[local-name() = $name]/@*" mode="insertConfig" />
              <xsl:apply-templates
                select="* | comment() | text()" mode="insertConfig">
                <xsl:with-param name="elem" select="$elem/*[local-name() = $name][1]" /> <!-- only one element is expected-->
                <xsl:with-param name="fileType" select="$fileType" />
              </xsl:apply-templates>
            </xsl:copy>
          </xsl:when>
          <xsl:otherwise>
            <xsl:message>  TODO: multiple elements and not placeholder - insert both <xsl:value-of select="local-name()"/></xsl:message>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:when>
      <xsl:otherwise> <!-- element is present only in config-->
        <xsl:if test="not(@placeholder) 
                      and (not(@condition) 
                           or $type = @condition
                           or $fileType = @condition
                           or concat($fileType,'.',$type) = @condition
                           )">
          <xsl:copy>
            <xsl:apply-templates select="@*" mode="insertConfig" />
            <xsl:apply-templates select="* | comment() | text()" mode="insertConfig">
              <xsl:with-param name="fileType" select="$fileType" />
            </xsl:apply-templates>
          </xsl:copy>
        </xsl:if>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <xsl:template match="@condition" mode="insertConfig"/>
  <xsl:template match="@*" mode="insertConfig">
    <xsl:copy />
  </xsl:template>
  <xsl:template match="text()" mode="insertConfig">
    <xsl:copy />
  </xsl:template>

  

  <xsl:template name="add-tagsDecl">
    <xsl:param name="tagUsages" />
    <xsl:variable name="context"
      select="./tei:tagsDecl/tei:namespace[@name='http://www.tei-c.org/ns/1.0']" />
    <xsl:element
      name="tagsDecl">
      <xsl:element name="namespace">
        <xsl:attribute name="name">http://www.tei-c.org/ns/1.0</xsl:attribute>
        <xsl:for-each select="distinct-values(($tagUsages//@gi,$context//@gi))">
          <xsl:sort select="." />
          <xsl:variable name="elem-name" select="." />
          <xsl:copy-of copy-namespaces="no" select="$tagUsages//*:tagUsage[@gi=$elem-name]" />
        </xsl:for-each>
      </xsl:element>
    </xsl:element>
  </xsl:template>

  <xsl:template name="add-measure-words">
    <xsl:param name="quantity" />
    <xsl:call-template name="add-measure">
      <xsl:with-param name="quantity" select="$quantity" />
      <xsl:with-param name="unit">words</xsl:with-param>
      <xsl:with-param name="en_text">words</xsl:with-param>
      <!-- <xsl:with-param name="uk_text">слів</xsl:with-param> -->
      <xsl:with-param name="cs_text">slov</xsl:with-param>
    </xsl:call-template>
  </xsl:template>

  <xsl:template name="add-measure">
    <xsl:param name="quantity" />
    <xsl:param name="unit" />
    <xsl:param name="en_text" />
    <xsl:param
      name="cs_text" />
    <xsl:element name="measure">
      <xsl:attribute name="unit" select="$unit" />
      <xsl:attribute name="quantity"
        select="mk:number($quantity)" />
      <xsl:attribute name="xml:lang">en</xsl:attribute>
      <xsl:value-of select="concat(mk:number($quantity),' ',$en_text)" />
    </xsl:element>
    <xsl:element
      name="measure">
      <xsl:attribute name="unit" select="$unit" />
      <xsl:attribute name="quantity" select="mk:number($quantity)" />
      <xsl:attribute name="xml:lang">cs</xsl:attribute>
      <xsl:value-of select="concat(mk:number($quantity),' ',$cs_text)" />
    </xsl:element>
  </xsl:template>

<!-- FUNCTIONS -->
  <xsl:function name="mk:number">
    <xsl:param name="num"/>
    <xsl:value-of select="format-number($num,'#0')"/>
  </xsl:function>

  <xsl:function name="mk:ana-href" as="xs:string">
    <xsl:param name="href"/>
    <xsl:sequence select="replace($href, '\.xml$', '.ana.xml')"/>
  </xsl:function>
</xsl:stylesheet>