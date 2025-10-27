<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="2.0"
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:xs="http://www.w3.org/2001/XMLSchema"
  xmlns:tei="http://www.tei-c.org/ns/1.0"
  xmlns="http://www.tei-c.org/ns/1.0"
  exclude-result-prefixes="xs tei">

  <xsl:param name="outFile"/>
  <xsl:output method="xml" indent="yes"/>

  <xsl:template match="/">
    <xsl:result-document href="{$outFile}" method="xml" indent="yes">
      <xsl:apply-templates select="node()|@*"/>
    </xsl:result-document>
  </xsl:template>

  <xsl:template match="@*|node()">
    <xsl:copy>
      <xsl:apply-templates select="@*|node()"/>
    </xsl:copy>
  </xsl:template>

  <xsl:template match="tei:lb">
    <xsl:choose>
      <!-- previous text node ends with hyphen -->
      <xsl:when test="preceding-sibling::node()[1][self::text()][substring(., string-length(.))='-']">
        <xsl:variable name="prev" select="preceding-sibling::node()[1]"/>
        <xsl:value-of select="substring($prev, 1, string-length($prev) - 1)"/>
      </xsl:when>

      <!-- first child of parent -->
      <xsl:when test="not(preceding-sibling::node()[self::node()])">
        <!-- remove lb silently -->
      </xsl:when>

      <!-- default — replace with space -->
      <xsl:otherwise>
        <xsl:text> </xsl:text>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

</xsl:stylesheet>
