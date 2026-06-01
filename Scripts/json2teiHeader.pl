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
  $bibl->addNewChild(undef,'date')->setAttribute('when', $opts{date});

  for my $idno (PressMintCZ::get_all_ids($json)){
    print STDERR "IDNO:\t",join(' ',%$idno),"\n";
    my $node_idno = $bibl->addNewChild(undef,'idno');
    $node_idno->setAttribute('type',$idno->{type});
    $node_idno->setAttribute('subtype',$idno->{subtype}) if exists $idno->{subtype};
    $node_idno->appendText($idno->{value})
  }

  my $physicalLocation = PressMintCZ::get_physical_location($json);
  if($physicalLocation) {
    my $msIdentifier = $bibl->addNewChild(undef,'msIdentifier');
    $msIdentifier->addNewChild(undef, 'settlement')->appendText($physicalLocation->{settlement});
    $msIdentifier->addNewChild(undef, 'repository')->appendText($physicalLocation->{repository});
    for my $shelf (@{$physicalLocation->{shelfmark}}) {
      my $idno = $msIdentifier->addNewChild(undef, 'idno');
      $idno->setAttribute('type','shelfmark');
      $idno->appendText($shelf);
    }
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