#!/usr/bin/env perl
use strict;
use warnings;
use utf8;
use feature 'unicode_strings';
use open qw(:std :utf8);
use File::Spec;
use XML::LibXML;
use JSON qw(encode_json);


use PressMintCZ;


my $args = PressMintCZ::parse_args(\@ARGV, [
]);


PressMintCZ::process_issues(
  \&idMapping,
  %$args
);


sub idMapping {
  my $json = shift;
  my %opts = @_;
  print STDERR "INFO: Running ocr on $opts{'input-uuid-path'}\n";
  my @pages = PressMintCZ::get_page($json);
  $opts{id} = PressMintCZ::create_comp_id($json);
  $opts{date} = PressMintCZ::get_comp_date($json);
  $opts{year} = PressMintCZ::get_comp_year($json);
  my $outDir = File::Spec->catdir($opts{"output-dir"},$opts{year});
  my $outJSONL = File::Spec->catfile($outDir,$opts{id}.".jsonl");
  my $pb_n = 0;
  `mkdir -p $outDir`;
  open my $outFH, '>>', $outJSONL or die $!;
  for my $page (@pages) {
    $pb_n++;
    my $page_uuid = PressMintCZ::get_page_uuid($page);
    my $pid = "$opts{id}.facs$pb_n";
    my $purl = PressMintCZ::get_facs_url($page);
    my %row = (
      n         => $pb_n,
      uuid      => $page_uuid,
      uuid_path => "$opts{'input-uuid-path'}/$page_uuid",
      teiid     => $pid,
      url       => $purl,
    );
    print $outFH encode_json(\%row), "\n";
  }
  close $outFH or die $!;
}
