#!/usr/bin/env perl
use strict;
use warnings;
use utf8;
use open qw(:std :utf8);
use File::Spec;
use XML::LibXML;

use PressMintCZ;


my $args = PressMintCZ::parse_args(\@ARGV, [
    'input-text-dir=s',
    'input-format=s',
    'input-file-suffix=s',
]);


PressMintCZ::process_issues(
  \&convert2text,
  %$args
);


sub convert2text {
  my $json = shift;
  my %opts = @_;
  print STDERR "INFO: processing $opts{'input-uuid-path'}\n";
  my @pages = PressMintCZ::get_page($json);
  $opts{id} = PressMintCZ::create_comp_id($json);;
  $opts{date} = PressMintCZ::get_comp_date($json);;
  $opts{year} = PressMintCZ::get_comp_year($json);;
  my $xml = do { local $/; <DATA> };
  my $parser = XML::LibXML->new();
  my $dom = $parser->parse_string($xml);
  my $xpc = XML::LibXML::XPathContext->new($dom);
  $xpc->registerNs('tei', 'http://www.tei-c.org/ns/1.0');
  my ($tei) = $xpc->findnodes('/tei:TEI');
  $tei->setAttribute('xml:id',$opts{id});
  my ($body) = $xpc->findnodes('//tei:body');
  my ($facs) = $xpc->findnodes('//tei:facsimile');
  my $pb_n=0;
  for my $page (@pages) {
    $pb_n++;
    my $page_uuid = PressMintCZ::get_page_uuid($page);
    my $pb = $body->addNewChild(undef, 'pb');
    $pb->setAttribute('facs',"#$opts{id}.facs$pb_n");
    $pb->setAttribute('n',"$pb_n");
    $pb->setAttribute('source',PressMintCZ::get_page_url($page));

    my $surf = $facs->addNewChild(undef, 'surface');
    $surf->setAttribute('xml:id',"$opts{id}.facs$pb_n");
    my $graphic = $surf->addNewChild(undef,'graphic');
    $graphic->setAttribute('url',PressMintCZ::get_facs_url($page));
    if($opts{'input-format'} eq 'txt') {
      my $text = PressMintCZ::read_text_file(File::Spec->catfile($opts{'input-text-dir'},$opts{'input-uuid-path'},"$page_uuid$opts{'input-file-suffix'}"));
      convertTxtPage($body,$text);
    } else {
      print STDERR "ERROR: unsuported input format $opts{'input-format'}\n";
    }

  }
  PressMintCZ::save_xml($dom,%opts);
}


sub convertTxtPage {
  my ($body,$text) = @_;
  my $lb_n = 0;
  for my $line (split /\n/, $text) {
    $lb_n++;
    my $lb = $body->addNewChild(undef, 'lb');
    $lb->setAttribute('n',"$lb_n");
    $body->appendText($line);
  }
}


__DATA__
<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0"
     xml:lang="cs">
   <facsimile/>
   <text>
     <body/>
   </text>
</TEI>