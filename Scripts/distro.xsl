<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet version="2.0"
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:xi="http://www.w3.org/2001/XInclude"
  xmlns:xs="http://www.w3.org/2001/XMLSchema"
  xmlns:tei="http://www.tei-c.org/ns/1.0"
  xmlns="http://www.tei-c.org/ns/1.0"
  xmlns:mk="http://ufal.mff.cuni.cz/matyas-kopp"
  exclude-result-prefixes="xs tei xi mk">

  <xsl:output method="xml" indent="yes" encoding="UTF-8" suppress-indentation="w pc"/>

  <xsl:param name="outDir" />
  <xsl:param name="inComponentDir" />
  <xsl:param name="inHeaderDir" />
  <xsl:param name="anaDir" />
  <xsl:param name="inTaxonomiesDir" />
  <xsl:param name="type" /> <!-- TEI or TEI.ana-->
  <xsl:param name="projectConfig" />

  <xsl:output method="xml" indent="yes" encoding="UTF-8" />
  <xsl:preserve-space elements="catDesc seg p" />

  <xsl:variable name="config">
    <xsl:message>READING CONFIG <xsl:value-of select="$projectConfig" /></xsl:message>
    <xsl:copy-of
      select="document($projectConfig)/tei:config/*" />
  </xsl:variable>

  <xsl:variable name="today" select="format-date(current-date(), '[Y0001]-[M01]-[D01]')" />

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

  <xsl:variable name="url-corpus-ana"
    select="concat($anaDir, '/', replace(base-uri(), '.*/(.+)\.xml', '$1.ana.xml'))" />

  <xsl:variable name="suff">
    <xsl:choose>
      <xsl:when test="$type = 'TEI.ana'">.ana</xsl:when>
      <xsl:otherwise><text /></xsl:otherwise>
    </xsl:choose>
  </xsl:variable>

  <!-- Gather URIs of component xi + files and map to new files, incl. .ana files -->
  <xsl:variable name="docs">
    <xsl:for-each select="/tei:teiCorpus/xi:include">
      <item>
        <xi-orig>
          <xsl:value-of select="@href" />
        </xi-orig>
        <url-orig>
          <xsl:value-of select="concat($inComponentDir, '/', @href)" />
        </url-orig>
        <doc>
          <xsl:variable name="docWithHeader">
            <xsl:apply-templates select="document(concat($inComponentDir, '/', @href))"
              mode="insertHeader">
              <xsl:with-param name="teiHeader"
                select="document(concat($inHeaderDir, '/', @href))/tei:TEI/tei:teiHeader" />
              <xsl:with-param name="fileType">comp</xsl:with-param>
            </xsl:apply-templates>
          </xsl:variable>
          <xsl:apply-templates mode="compCleanup" select="$docWithHeader"/>
        </doc>
        <url-new>
          <xsl:value-of select="concat($outDir, '/')" />
          <xsl:choose>
            <xsl:when test="$type = 'TEI.ana'"><xsl:value-of
                select="replace(@href,'\.xml$','.ana.xml')" /></xsl:when>
            <xsl:when test="$type = 'TEI'"><xsl:value-of select="@href" /></xsl:when>
          </xsl:choose>
        </url-new>
        <xi-new>
          <xsl:choose>
            <xsl:when test="$type = 'TEI.ana'"><xsl:value-of
                select="replace(@href,'\.xml$','.ana.xml')" /></xsl:when>
            <xsl:when test="$type = 'TEI'"><xsl:value-of select="@href" /></xsl:when>
          </xsl:choose>
        </xi-new>
        <url-ana>
          <xsl:value-of select="concat($anaDir, '/', replace(@href, '\.xml', '.ana.xml'))" />
        </url-ana>
      </item>
    </xsl:for-each>
  </xsl:variable>

  <!-- Numbers of words in component .ana files -->
  <xsl:variable name="words">
    <xsl:for-each select="$docs/tei:item">
      <item n="{tei:xi-orig}">
        <xsl:choose>
          <!-- For .ana files, compute number of words -->
          <xsl:when test="$type = 'TEI.ana'">
            <xsl:value-of select="count(tei:doc//tei:w[not(parent::tei:w)])" />
          </xsl:when>
          <!-- For plain files, take number of words from .ana files -->
          <xsl:when test="doc-available(tei:url-ana)">
            <xsl:value-of
              select="document(tei:url-ana)/tei:TEI/tei:teiHeader//
                                  tei:extent/tei:measure[@unit='words'][1]/@quantity" />
          </xsl:when>
          <xsl:otherwise>
            <xsl:message
              select="concat('ERROR ', /tei:TEI/@xml:id,
                                   ': cannot locate .ana file ', tei:url-ana)" />
            <xsl:value-of
              select="number('0')" />
          </xsl:otherwise>
        </xsl:choose>
      </item>
    </xsl:for-each>
  </xsl:variable>

  <!-- Numbers of tokens in component .ana files -->
  <xsl:variable name="tokens">
    <xsl:for-each select="$docs/tei:item">
      <xsl:variable name="doc" select="./tei:doc" />
      <item n="{tei:xi-orig}">
        <!-- For .ana files, compute number of tokens -->
        <xsl:if test="$type = 'TEI.ana'">
          <xsl:value-of
            select="$doc/
                                    count(
                                           .//tei:w[not(parent::tei:w)]
                                           | .//tei:pc
                                         )" />
        </xsl:if>
      </item>
    </xsl:for-each>
  </xsl:variable>

  <!-- Dates in component files -->
  <xsl:variable name="dates">
    <xsl:for-each select="$docs/tei:item">
      <item n="{tei:xi-orig}">
        <xsl:value-of select="tei:doc/tei:TEI/tei:teiHeader//tei:sourceDesc/tei:bibl/tei:date/@when" />
      </item>
    </xsl:for-each>
  </xsl:variable>
  <xsl:variable name="corpusFrom"
    select="replace(min($dates/tei:item/translate(.,'-','')),'(....)(..)(..)','$1-$2-$3')" />
  <xsl:variable name="corpusTo"
    select="replace(max($dates/tei:item/translate(.,'-','')),'(....)(..)(..)','$1-$2-$3')" />

  <!-- -->
  <xsl:variable name="titles">
    <xsl:for-each select="$docs/tei:item">
      <item n="{tei:xi-orig}">
        <xsl:value-of select="normalize-space(tei:doc/tei:TEI/tei:teiHeader//tei:sourceDesc/tei:bibl/tei:title/text())" />
      </item>
    </xsl:for-each>
  </xsl:variable>

  <!-- calculate tagUsages in component files -->
  <xsl:variable name="tagUsages">
    <xsl:for-each select="$docs/tei:item">
      <item n="{tei:xi-orig}">
        <xsl:variable name="context-node" select="." />
        <xsl:for-each
          select="tei:doc/
                            distinct-values(tei:TEI/tei:text/descendant-or-self::tei:*/name())">
          <xsl:sort select="." />
          <xsl:variable name="elem-name" select="." />
          <!--item
          n="{$elem-name}">
              <xsl:value-of select="$context-node/tei:doc/
                                    count(tei:TEI/tei:text/descendant-or-self::tei:*[name()=$elem-name])"/>
          </item-->
          <xsl:element
            name="tagUsage">
            <xsl:attribute name="gi" select="$elem-name" />
            <xsl:attribute name="occurs"
              select="$context-node/tei:doc/
                                    count(tei:TEI/tei:text/descendant-or-self::tei:*[name()=$elem-name])" />
          </xsl:element>
        </xsl:for-each>
      </item>
    </xsl:for-each>
  </xsl:variable>


  <xsl:template match="/">
    <xsl:message select="concat('INFO: Starting to process ', tei:teiCorpus/@xml:id)" />
    <!-- Process component files -->
    <xsl:for-each
      select="$docs//tei:item">
      <xsl:variable name="this" select="tei:xi-orig" />
      <xsl:message
        select="concat('INFO: Processing ', $this)" />
      <xsl:result-document href="{tei:url-new}">
        <xsl:apply-templates mode="comp" select="tei:doc/tei:TEI">
          <xsl:with-param name="words" select="$words/tei:item[@n = $this]" />
          <xsl:with-param name="tagUsages" select="$tagUsages/tei:item[@n = $this]" />
          <xsl:with-param name="date" select="$dates/tei:item[@n = $this]/text()" />
          <xsl:with-param name="title" select="$titles/tei:item[@n = $this]" />
        </xsl:apply-templates>
      </xsl:result-document>
      <xsl:message
        select="concat('INFO: Saving to ', tei:xi-new)" />
    </xsl:for-each>
    <!-- Output Root file -->
    <xsl:message>INFO: processing root </xsl:message>
    <xsl:result-document href="{$outRoot}">
      <xsl:message>ROOT is not implemented</xsl:message>
      <xsl:variable name="corpus">
        <xsl:apply-templates select="." mode="insertHeader">
          <xsl:with-param name="fileType">root</xsl:with-param>
        </xsl:apply-templates>
      </xsl:variable>
      <xsl:apply-templates mode="root" select="$corpus"/>
    </xsl:result-document>
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
    <xsl:copy>
      <xsl:call-template name="add-measure-words">
        <xsl:with-param name="quantity" select="sum($words/tei:item)" />
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
    <xsl:copy>
      <xsl:apply-templates select="@*" mode="root"/>
      <xsl:apply-templates select="tei:*" mode="root"/>
      <xsl:for-each select="xi:include">
        <xsl:sort select="@href"/>
        <xsl:variable name="href" select="@href"/>
        <xsl:variable name="new-href" select="$docs/tei:item[./tei:xi-orig/text() = $href]/tei:xi-new/text()"/>
        <xsl:message select="concat('INFO: Fixing xi:include: ',$href,' ',$new-href)"/>
        <xsl:copy>
          <xsl:attribute name="href" select="$new-href"/>
        </xsl:copy>
      </xsl:for-each>
    </xsl:copy>
  </xsl:template>


  <xsl:template mode="root" match="tei:tagsDecl">
    <xsl:call-template name="add-tagsDecl">
      <xsl:with-param name="tagUsages">
        <xsl:for-each select="distinct-values($tagUsages//@gi)">
          <xsl:sort select="."/>
          <xsl:variable name="elem-name" select="."/>
          <tagUsage gi="{$elem-name}" occurs="{mk:number(sum($tagUsages//*[@gi=$elem-name]/@occurs))}"/>
        </xsl:for-each>
      </xsl:with-param>
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
</xsl:stylesheet>