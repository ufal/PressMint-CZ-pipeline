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
  \&getComponentPath,
  %$args
);


sub getComponentPath {
  my $json = shift;
  my %opts = @_;
  $opts{id} = PressMintCZ::create_comp_id($json);
  $opts{date} = PressMintCZ::get_comp_date($json);
  $opts{year} = PressMintCZ::get_comp_year($json);
  my $componentPath = "$opts{year}/$opts{id}";
  print "$componentPath\n";
}
