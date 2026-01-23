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
    'output-xml-dir=s',
    'output-alto-dir=s',
]);


PressMintCZ::process_issues(
  \&runOCR,
  %$args
);


sub runOCR {
  my $json = shift;
  my %opts = @_;
  print STDERR "INFO: Running ocr on $opts{'input-uuid-path'}\n";
  my @pages = PressMintCZ::get_page($json);
  $opts{id} = PressMintCZ::create_comp_id($json);
  $opts{date} = PressMintCZ::get_comp_date($json);
  $opts{year} = PressMintCZ::get_comp_year($json);
  my $outXmlDir = File::Spec->catdir($opts{"output-xml-dir"},$opts{year},$opts{id});
  my $outAltoDir = File::Spec->catdir($opts{"output-alto-dir"},$opts{year},$opts{id});
  print "ID=$opts{id}\n";
  print "OUTPUT XML DIR=$outXmlDir\n";
  print "OUTPUT Alto DIR=$outAltoDir\n";
  my $cmd = "python3 -m pero_ocr.user_scripts.parse_folder \\
	    --config ".$opts{model}." \\
	    --device ".$opts{device}." \\
	    --input-image-path ".File::Spec->catfile($opts{'input-img-dir'},$opts{'input-uuid-path'})." \\
	    --output-xml-path $outXmlDir \\
	    --output-alto-path $outAltoDir";
	#		--output-render-order \\
  # 	--output-render-path $outDir/RENDER \\
	#   --output-line-path $outDir/LINE \\
	#   --output-logit-path $outDir/LOGIT \\
  #   --output-transcriptions-file-path $outDir/TRANSCRIPTIONS_FILE
  `$cmd`;
}
