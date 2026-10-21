#!/usr/bin/env perl
use strict;
use warnings;
use utf8;
use open qw(:std :utf8);
use File::Spec;
use XML::LibXML;
use feature 'state';

use PressMintCZ;


my $args = PressMintCZ::parse_args(\@ARGV, []);

PressMintCZ::process_issues(
  \&convert2header,
  %$args
);


sub convert2header{
  my $json = shift;
  my %opts = @_;
  print STDERR "INFO: processing $opts{'input-uuid-path'}\n";
  $opts{id} = PressMintCZ::create_comp_id($json);
  $opts{date} = PressMintCZ::get_comp_date($json);
  $opts{year} = PressMintCZ::get_comp_year($json);
  state $xml = do { local $/; <DATA> };
  my $parser = XML::LibXML->new();
  my $dom = $parser->parse_string($xml);
  my $xpc = XML::LibXML::XPathContext->new($dom);
  $xpc->registerNs('tei', 'http://www.tei-c.org/ns/1.0');
  my ($tei) = $xpc->findnodes('/tei:TEI');
  $tei->setAttribute('xml:id',$opts{id});
  my ($titleStmt) = $xpc->findnodes('//tei:titleStmt');
  my ($bibl) = $xpc->findnodes('//tei:bibl');
  my $jtitle = $bibl->addNewChild(undef,'title');
  $jtitle->setAttribute('level', 'j');
  $jtitle->appendText(PressMintCZ::get_journal_name($json));
  # editor element is not in PressMint schema
  for my $editor (PressMintCZ::get_editors($json)){
    my $respStmt = $bibl->addNewChild(undef,'respStmt');
    $respStmt->addNewChild(undef,'persName')->appendText($editor);
    $respStmt->addNewChild(undef,'resp')->appendText('redaktor');
    my $resp_en = $respStmt->addNewChild(undef,'resp');
    $resp_en->setAttribute('xml:lang','en');
    $resp_en->appendText('editor');
  }
  for my $place (PressMintCZ::get_pub_places($json)){
    $bibl->addNewChild(undef,'pubPlace')->appendText($place);
  }
  for my $publisher (PressMintCZ::get_publishers($json)){
    $bibl->addNewChild(undef,'publisher')->appendText($publisher);
  }
  $bibl->addNewChild(undef,'date')->setAttribute('when', $opts{date});
  for my $unit (qw/volume issue/){
    my $number = $unit eq 'volume' ? PressMintCZ::get_volume_number($json) : PressMintCZ::get_issue_number($json);
    next unless defined $number && $number ne '';
    my $biblScope = $bibl->addNewChild(undef,'biblScope');
    $biblScope->setAttribute('unit', $unit);
    $biblScope->appendText($number);
  }

  for my $idno (PressMintCZ::get_all_ids($json)){
    print STDERR "IDNO:\t",join(' ',%$idno),"\n";
    my $node_idno = $bibl->addNewChild(undef,'idno');
    $node_idno->setAttribute('type',$idno->{type});
    $node_idno->setAttribute('subtype',$idno->{subtype}) if exists $idno->{subtype};
    $node_idno->appendText($idno->{value})
  }

  PressMintCZ::save_xml($dom,%opts);
}


__DATA__
<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0"
     xml:lang="cs">
   <teiHeader>
     <fileDesc>
       <titleStmt/>
       <sourceDesc>
         <bibl/>
       </sourceDesc>
     </fileDesc>
   </teiHeader>
</TEI>