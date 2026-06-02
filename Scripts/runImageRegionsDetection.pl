#!/usr/bin/env perl
use strict;
use warnings;
use utf8;
use feature 'unicode_strings';
use open qw(:std :utf8);
use File::Spec;
use XML::LibXML;

use PressMintCZ;


my $args = PressMintCZ::parse_args(\@ARGV, [
    'input-img-dir=s',
    'input-file-suffix=s',
    'model=s',
    'device=s',
]);


PressMintCZ::process_issues(
  \&runImageRegionsDetection,
  %$args
);


sub runImageRegionsDetection {
  my $json = shift;
  my %opts = @_;
  print STDERR "INFO: Running region detection on $opts{'input-uuid-path'}\n";
  my @pages = PressMintCZ::get_page($json);
  $opts{id} = PressMintCZ::create_comp_id($json);
  $opts{date} = PressMintCZ::get_comp_date($json);
  $opts{year} = PressMintCZ::get_comp_year($json);
  my $outFile = File::Spec->catdir($opts{"output-dir"},$opts{year},$opts{id}.".jsonl");
  print "ID=$opts{id}\n";
  print "OUTPUT DIR=".File::Spec->catdir($opts{"output-dir"},$opts{year},$opts{id})."\n";
  my $cmd = "python3 Scripts/yoloLayout.py \\
	    --model ".$opts{model}." \\
	    --device ".$opts{device}." \\
	    --images ".File::Spec->catfile($opts{'input-img-dir'},$opts{'input-uuid-path'})." \\
	    --uuidpath ".$opts{'input-uuid-path'}." \\
	    --output $outFile";
  print `$cmd`;
}
