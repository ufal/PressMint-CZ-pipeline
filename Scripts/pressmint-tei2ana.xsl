<?xml version="1.0" encoding="utf-8"?>
<!-- Patch root file PressMint-XX.xml of fixed TEI corpus to root file PressMint-XX.ana.xml of annotated corpus.
     Annotated components (*.ana.xml) are expected in $anaDir (copied there by Makefile.PressMint),
     components that are missing there are not included.
     Changes: teiCorpus/@xml:id and title suffixes, respStmt for linguistic annotation, xi:include hrefs,
     tagsDecl (counted from annotated components), NER taxonomy and appInfo. -->
<xsl:stylesheet version="3.0"
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:xi="http://www.w3.org/2001/XInclude"
  xmlns:xs="http://www.w3.org/2001/XMLSchema"
  xmlns:map="http://www.w3.org/2005/xpath-functions/map"
  xmlns:tei="http://www.tei-c.org/ns/1.0"
  xmlns="http://www.tei-c.org/ns/1.0"
  xmlns:mk="http://ufal.mff.cuni.cz/matyas-kopp"
  exclude-result-prefixes="xs map tei xi mk">

  <xsl:output method="xml" indent="yes" encoding="UTF-8"/>

  <xsl:param name="anaDir" />          <!-- PressMint-XX.TEI.ana directory -->
  <xsl:param name="nerTaxonomyHref" /> <!-- PressMint-taxonomy-NER.ana.xml -->
  <xsl:param name="udModel" />
  <xsl:param name="nerModel" />
  <xsl:param name="respName" />
  <xsl:param name="respRef" />

  <!-- components available in annotated version -->
  <xsl:variable name="components" as="xs:string*"
    select="/tei:teiCorpus/xi:include/mk:ana-href(@href)[doc-available(concat($anaDir, '/', .))]" />

  <!-- tagUsage summed over components (read one by one, not kept in memory) -->
  <xsl:variable name="tagUsages">
    <xsl:iterate select="$components">
      <xsl:param name="totals" as="map(xs:string, xs:integer)" select="map{}" />
      <xsl:on-completion>
        <xsl:for-each select="map:keys($totals)">
          <xsl:sort select="." />
          <tagUsage gi="{.}" occurs="{$totals(.)}" />
        </xsl:for-each>
      </xsl:on-completion>
      <xsl:variable name="counts" as="map(xs:string, xs:integer)">
        <xsl:source-document href="{concat($anaDir, '/', .)}" streamable="no">
          <xsl:map>
            <xsl:for-each-group select="tei:TEI/tei:text/descendant-or-self::tei:*" group-by="local-name()">
              <xsl:map-entry key="current-grouping-key()" select="count(current-group())" />
            </xsl:for-each-group>
          </xsl:map>
        </xsl:source-document>
      </xsl:variable>
      <xsl:next-iteration>
        <xsl:with-param name="totals"
          select="fold-left(map:keys($counts), $totals,
                    function($m, $k) { map:put($m, $k, ($m($k), 0)[1] + $counts($k)) })" />
      </xsl:next-iteration>
    </xsl:iterate>
  </xsl:variable>

  <xsl:template match="/">
    <xsl:variable name="skipped" select="count(/tei:teiCorpus/xi:include) - count($components)" />
    <xsl:if test="$skipped > 0">
      <xsl:message select="concat('WARN: ', $skipped, ' component(s) missing in ', $anaDir, ', not included')" />
    </xsl:if>
    <xsl:apply-templates />
  </xsl:template>

  <xsl:template match="*">
    <xsl:copy>
      <xsl:apply-templates select="@* | node()" />
    </xsl:copy>
  </xsl:template>

  <xsl:template match="@* | comment() | processing-instruction() | text()">
    <xsl:copy />
  </xsl:template>

  <xsl:template match="tei:teiCorpus/@xml:id">
    <xsl:attribute name="xml:id" select="concat(., '.ana')" />
  </xsl:template>

  <xsl:template match="tei:titleStmt/tei:title//text()">
    <xsl:value-of select="replace(., '\[PressMint(\s|\])', '[PressMint.ana$1')" />
  </xsl:template>

  <!-- new respStmt after last respStmt (or title, or as last child) -->
  <xsl:template match="tei:titleStmt">
    <xsl:variable name="last" select="((tei:respStmt | tei:title)[last()], node()[last()])[1]" />
    <xsl:copy>
      <xsl:apply-templates select="@*" />
      <xsl:for-each select="node()">
        <xsl:apply-templates select="." />
        <xsl:if test=". is $last">
          <respStmt>
            <persName>
              <xsl:if test="$respRef != ''"><xsl:attribute name="ref" select="$respRef" /></xsl:if>
              <xsl:value-of select="$respName" />
            </persName>
            <resp xml:lang="en">Linguistic annotation</resp>
          </respStmt>
        </xsl:if>
      </xsl:for-each>
    </xsl:copy>
  </xsl:template>

  <xsl:template match="tei:tagsDecl/tei:namespace[@name = 'http://www.tei-c.org/ns/1.0']">
    <xsl:copy>
      <xsl:apply-templates select="@*" />
      <xsl:copy-of select="$tagUsages/tei:tagUsage" />
    </xsl:copy>
  </xsl:template>

  <xsl:template match="tei:encodingDesc">
    <xsl:copy>
      <xsl:apply-templates select="@* | node()" />
      <xsl:if test="not(tei:classDecl)">
        <classDecl><xi:include href="{$nerTaxonomyHref}" /></classDecl>
      </xsl:if>
      <xsl:if test="not(tei:appInfo)">
        <appInfo><xsl:call-template name="applications" /></appInfo>
      </xsl:if>
    </xsl:copy>
  </xsl:template>

  <xsl:template match="tei:encodingDesc/tei:classDecl[1]">
    <xsl:copy>
      <xsl:apply-templates select="@* | node()" />
      <xsl:if test="not(xi:include[@href = $nerTaxonomyHref])">
        <xi:include href="{$nerTaxonomyHref}" />
      </xsl:if>
    </xsl:copy>
  </xsl:template>

  <xsl:template match="tei:encodingDesc/tei:appInfo[1]">
    <xsl:copy>
      <xsl:apply-templates select="@* | node()" />
      <xsl:call-template name="applications" />
    </xsl:copy>
  </xsl:template>

  <xsl:template match="tei:teiCorpus/xi:include">
    <xsl:variable name="href" select="mk:ana-href(@href)" />
    <xsl:if test="$href = $components">
      <xi:include href="{$href}" />
    </xsl:if>
  </xsl:template>

  <xsl:template name="applications">
    <application ident="UDPipe" version="2">
      <label>UDPipe 2 (<xsl:value-of select="$udModel" /> model)</label>
      <desc xml:lang="en">Tokenization, sentence segmentation, POS tagging and lemmatization done with UDPipe 2 (<ref target="http://ufal.mff.cuni.cz/udpipe/2">http://ufal.mff.cuni.cz/udpipe/2</ref>) with <xsl:value-of select="$udModel" /> model.</desc>
    </application>
    <application ident="NameTag" version="3">
      <label>NameTag 3 (<xsl:value-of select="$nerModel" /> model)</label>
      <desc xml:lang="en">Name entity recognition done with NameTag 3 (<ref target="http://ufal.mff.cuni.cz/nametag/3">http://ufal.mff.cuni.cz/nametag/3</ref>) with <xsl:value-of select="$nerModel" /> model (categories PER, LOC, ORG, MISC).</desc>
    </application>
  </xsl:template>

  <xsl:function name="mk:ana-href" as="xs:string">
    <xsl:param name="href" />
    <xsl:sequence select="replace($href, '\.xml$', '.ana.xml')" />
  </xsl:function>
</xsl:stylesheet>
