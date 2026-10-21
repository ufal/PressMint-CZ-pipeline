package PressMintCZ;
use strict;
use warnings;
use Getopt::Long qw(GetOptionsFromArray);
use JSON;
use File::Spec;
use File::Path qw(make_path);
use Encode qw(decode);
use XML::LibXML;
use XML::LibXML::PrettyPrint;



# periodical/periodicalvolume/periodicalitem/page
my %known_types = map { $_ => 1 } qw/periodical periodicalvolume periodicalitem page/;

my $pp = XML::LibXML::PrettyPrint->new(
  indent_string => "  ",
  element => {
    inline   => [qw//],
    #block    => [qw//],
    #compact  => [qw//],
    preserves_whitespace => [qw/p/],
  }
);

sub parse_args {
  my ($argv_ref, $extra_opts) = @_;

  my %args;
  my @opt_specs = (
        'input-base-dir=s',
        'input-uuid-path=s',
        'output-dir=s',
  );

  push @opt_specs, @$extra_opts if $extra_opts && ref $extra_opts eq 'ARRAY';
    
  foreach my $spec (@opt_specs) {
    my ($name) = split(/[=:]/, $spec);
    $args{$name} = undef;
  }

  GetOptionsFromArray($argv_ref, \%args, @opt_specs) or die "Error parsing arguments\n";

  return \%args;
}

sub read_text_file {
  my ($path) = @_;
   # Check file existence and readability
  unless(-e $path) {
    print STDERR "ERROR: File not found: $path\n";
    return;
  }
  unless(-r $path) {
    print STDERR "ERROR: File not readable: $path\n";
    return;
  }
  # Read the file fully into a string
  open my $fh, '<:raw', $path
    or die "Cannot open $path: $!";
  local $/;  # enable slurp mode
  my $raw = <$fh>;
  close $fh;

   # Remove UTF-8 BOM if present
  $raw =~ s/^\x{FEFF}//;

  # Decode to Perl internal UTF-8
  my $text = decode('UTF-8', $raw);

  # Normalize line endings to Unix style
  $text =~ s/\r\n/\n/g;

  return $text
}

sub read_json_file {
  my ($path) = @_;
   # Check file existence and readability
  unless(-e $path) {
    print STDERR "ERROR: File not found: $path\n";
    return;
  }
  unless(-r $path) {
    print STDERR "ERROR: File not readable: $path\n";
    return;
  }
  # Read the file fully into a string
  open my $fh, '<:raw', $path
    or die "Cannot open $path: $!";
  local $/;  # enable slurp mode
  my $json_text = <$fh>;
  close $fh;
 
  # Parse JSON safely
  my $data = eval { decode_json($json_text) };
  if ($@) {
    print STDERR "ERROR: Error parsing JSON in $path: $@";
    return;
  }

  return $data;
}

sub save_xml {
  my $dom = shift;
  my %opts = @_;
  
  my $dir = File::Spec->catdir($opts{'output-dir'},$opts{year});
  my $file_path = File::Spec->catfile($dir,"$opts{id}.xml");
  if ($dir && !-d $dir) {
    make_path($dir) or die "ERROR: Failed to create directory $dir: $!";
  }

  # Write XML to file (UTF-8, pretty print)
  open my $fh, '>:raw', $file_path
    or die "ERROR: Cannot open $file_path for writing: $!";
  $pp->pretty_print($dom);
  my $raw = $dom->toString(1);
  print $fh $raw;
  close $fh;

  print "INFO: Saved XML to $file_path\n";
}


sub process_issues {
  my $callback = shift;
  my %opts = @_;
  my $json_file_path =  File::Spec->catfile($opts{'input-base-dir'},"$opts{'input-uuid-path'}.json");
  my $dir_path =  File::Spec->catdir($opts{'input-base-dir'},"$opts{'input-uuid-path'}");
  if(-e $json_file_path) {
    print STDERR "INFO: processing file $json_file_path\n";
    my $metadata = read_json_file($json_file_path); 
    return unless $metadata;
    my $metadata_type = get_metadata_type($metadata);
    if($metadata_type) {
      if ($metadata_type eq 'page') {
        print STDERR "ERROR: single page processing is not supported";
      } elsif($metadata_type eq 'periodicalitem') {
        print STDERR "INFO: processing $metadata_type $opts{'input-uuid-path'}\n";
        $callback->($metadata,%opts);
      } else {
        print STDERR "INFO: processing $metadata_type $opts{'input-uuid-path'}\n";
        # loop over inner volumes/issued and extend uuid_path
        my @child_uuids = get_child_uuids($metadata);
        for my $child_uuid (@child_uuids){
          process_issues($callback,%opts, 'input-uuid-path' => "$opts{'input-uuid-path'}/$child_uuid");
        }
      }
    }
  } elsif (-d $dir_path) {
    print STDERR "INFO: processing folder $dir_path\n";
    my %child_uuids = map {$_ => 1} grep {m/(.{8})-(.{4})-(.{4})-(.{4})-(.{12})/} map {s/.*\///;s/\.json$//;$_} grep {-d $_ || $_ =~ m/.json/} glob("$dir_path/*");
    for my $child_uuid (keys %child_uuids){
      process_issues($callback,%opts, 'input-uuid-path' => "$opts{'input-uuid-path'}/$child_uuid");
    }
  } else {
    print STDERR "ERROR: unexpected error\n";
  }
}

sub get_metadata_type {
  my $metadata = shift;
  my $type = $metadata->{model} // $metadata->{response}->{docs}->[0]->{'own_parent.model'};
  return unless $type && $known_types{$type};
  return $type;
}

sub get_child_uuids {
  my $metadata = shift;
  return map {$_->{pid} =~ /^uuid:(.*)/;$1} @{$metadata->{response}->{docs}};
}

sub get_page {
  my $metadata = shift;
  my  $type = get_metadata_type($metadata);
  unless ($type eq 'periodicalitem') {
    print STDERR "ERROR: unable to get page on $type\n";
    return;
  }
  return @{$metadata->{pages}}; #@{$metadata->{response}->{docs}};

}

sub get_page_uuid {
  my $page = shift;
  my $id = $page->{pid};
  $id =~ s/^uuid://;
  return $id;
}

sub get_journal_name {
  my $metadata = shift;
  return $metadata->{'root.title'};
}


my %id2type = (
  id_ccnb => 'local>čČNB',
  id_urnnbn => 'URN',
  # id_uuid is only in Národní nowiny and is equal to pid
  pid => 'local>UUID-mzk', 
  own_pid_path => 'local>UUID-path-mzk',
);

sub as_list {
  my $val = shift;
  return () unless defined $val;
  return ref $val eq 'ARRAY' ? @$val : ($val);
}

sub get_all_ids {
  my $metadata = shift;
  my $periodical = get_periodical($metadata);
  return (
    # ISSN is only in periodical record (lowercase check digit x in Kramerius index)
    (map { {type => 'ISSN', value => uc $_} } as_list($periodical->{id_issn})),
    (map {
      my $key = $_;
      my ($type,$subtype) = split />/, $id2type{$key};
      # ČNB is periodical level identifier, issues mostly do not have it
      my @values = as_list($metadata->{$key});
      @values = as_list($periodical->{$key}) if !@values && $key eq 'id_ccnb';
      map { {type => $type, $subtype ? (subtype => $subtype):(), value => $_}} @values
    } sort keys %id2type),
    (map { {
            type => 'URI',
            subtype => 'URL',
            value => "https://www.digitalniknihovna.cz/mzk/view/$_"
          } } as_list($metadata->{pid})),
    (map { {type => 'local', subtype => 'shelfmark', value => $_} } get_issue_or_periodical_values($metadata, 'shelf_locators')),

  );
}

# search records of the periodical and volume added by inputJsonMerge
sub get_periodical {
  my $metadata = shift;
  return $metadata->{periodical} // {};
}

sub get_volume {
  my $metadata = shift;
  return $metadata->{volume} // {};
}

sub get_volume_number {
  my $metadata = shift;
  return get_volume($metadata)->{'part.number.str'};
}

sub get_issue_number {
  my $metadata = shift;
  return $metadata->{'part.number.str'};
}

# issue level value, fallback to periodical level value
sub get_issue_or_periodical_values {
  my ($metadata, $key) = @_;
  my @values = as_list($metadata->{$key});
  @values = as_list(get_periodical($metadata)->{$key}) unless @values;
  return @values;
}

sub get_pub_places {
  my $metadata = shift;
  return get_issue_or_periodical_values($metadata, 'publication_places.facet');
}

sub get_publishers {
  my $metadata = shift;
  my @publishers = get_issue_or_periodical_values($metadata, 'publishers.facet');
  # periodical record lists all publishers over whole publication span without dates (e.g. 18 in Moravská orlice)
  # so it is not possible to decide which one published the issue
  if (@publishers > 1 && !as_list($metadata->{'publishers.facet'})) {
    print STDERR "WARN: skipping ambiguous publishers (",scalar(@publishers),") from periodical record\n";
    return;
  }
  return @publishers;
}

# periodical "authors" are editors (MODS role edt), name without life dates
sub get_editors {
  my $metadata = shift;
  return get_issue_or_periodical_values($metadata, 'authors.facet');
}


sub get_comp_date {
  my $metadata = shift;
  my $date = $metadata->{'date.min'} // $metadata->{response}->{docs}->[0]->{'date.min'};
  $date =~ s/T.*$//;
  return $date;
}

sub get_comp_year {
  my $metadata = shift;
  my $year = get_comp_date($metadata);
  $year =~ s/-.*$//;
  return $year;
}

sub create_comp_id {
  my $metadata = shift;
  my  $type = get_metadata_type($metadata);
  unless ($type eq 'periodicalitem') {
    print STDERR "ERROR: unable to create id on $type\n";
    return;
  }
  my $date = get_comp_date($metadata);
  my $uuid = $metadata->{pid} // $metadata->{response}->{docs}->[0]->{'own_parent.pid'};
  $uuid =~ s/^uuid://;
  $uuid =~ s/-.*$//; # remove suffix after first dash (shortening id)

  return "PressMint-CZ_$date-$uuid";
}


sub get_page_url {
  my $page = shift;
  my $id = $page->{pid};
  return "https://api.kramerius.mzk.cz/search/api/client/v7.0/items/$id/ocr/text";
}


sub get_facs_url {
  my $page = shift;
  my $id = $page->{pid};
  return "https://api.kramerius.mzk.cz/search/iiif/$id/full/max/0/default.jpg";
}
1;