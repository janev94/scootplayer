#!/usr/bin/env python2.7

from lxml import etree
import aniso8601
import os
import Queue
import re
import requests


class Representations(object):
    """
    Object containing the different representations available to the
    player.

    """

    representations = None
    initialisations = None
    min_buffer = 0
    max_duration = 0
    player = None

    def __init__(self, player, manifest):
        """Load the representations from the MPD."""
        self.player = player
        self.representations = list()
        self.initialisations = list()
        self.load_mpd(manifest)
        self.initialise()

    def stop(self):
        self.representations = list()
        self.initialistations = list()
        self.player.event('stop', 'representations')

    def _get_remote_mpd(self, url):
        """Download a remote MPD if necessary."""
        self.player.event('start', 'fetching remote mpd')
        response = requests.get(url)
        filename = os.path.basename(url)
        path = self.player.create_directory('/mpd')
        _file = open(path + filename, 'w')
        _file.write(response.content)
        self.player.event('stop', 'fetching remote mpd')
        return path + filename

    def load_mpd(self, manifest):
        """Load an MPD from file."""
        self.player.event('start', 'parsing mpd')
        expression = r'''http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|
            (?:%[0-9a-fA-F][0-9a-fA-F]))+'''
        url = re.search(expression, manifest)
        if url:
            manifest = self._get_remote_mpd(url.group())
        if self.player.options.xml_validation:
            document = self._validate_mpd(manifest)
        else:
            document = etree.parse(manifest)
        mpd = document.getroot()
        base_url = self.BaseURL()
        self.min_buffer = int(float(mpd.attrib['minBufferTime'][2:-1]))
        self.parse_mpd(base_url, mpd)
        sorted(self.representations, key=lambda representation:
               representation['bandwidth'])
        self.player.event('stop', 'parsing mpd')

    def _validate_mpd(self, manifest):
        """Validate the integrity of the schema and MPD."""
        schema = open('validation/DASH-MPD.xsd')
        schema = etree.parse(schema)
        self.player.event('start', 'validating schema')
        try:
            schema = etree.XMLSchema(schema)
        except etree.XMLSchemaParseError as e:
            self.player.event('error', str(e))
            raise SystemExit()
        self.player.event('stop', 'validating schema')
        try:
            document = etree.parse(manifest)
        except etree.XMLSyntaxError as e:
            self.player.event('error', str(e))
            raise SystemExit()
        self.player.event('start', 'validating document')
        try:
            schema.assertValid(document)
        except etree.DocumentInvalid as e:
            self.player.event('error', str(e))
            raise SystemExit()
        self.player.event('stop', 'validating document')
        return document

    def parse_mpd(self, base_url, parent_element):
        """Parse 'mpd' level XML."""
        try:
            self._set_duration(parent_element.get('mediaPresentationDuration'))
        except Exception:
            self.duration = 0
        # print parent_element('mediaPresentationDuration')
        for child_element in parent_element:
            if 'BaseURL' in child_element.tag:
                base_url.mpd = child_element.text
            self.parse_period(base_url, child_element)
        base_url.mpd = ''

    def _set_duration(self, duration):
        self._duration = aniso8601.parse_duration(duration).seconds

    def duration(self):
        return int(self._duration)

    def parse_period(self, base_url, parent_element):
        """Parse 'period' level XML."""
        for child_element in parent_element:
            if 'BaseURL' in child_element.tag:
                base_url.period = child_element.text
            self.parse_adaption_set(base_url, child_element)
        base_url.period = ''

    def parse_adaption_set(self, base_url, parent_element):
        """Parse 'adaption set' level XML."""
        for child_element in parent_element:
            if 'BaseURL' in child_element.tag:
                base_url.adaption_set = child_element.text
            if 'Representation' in child_element.tag:
                bandwidth = int(child_element.attrib['bandwidth'])
                try:
                    id_ = int(child_element.attrib['id'])
                except KeyError:
                    print 'id not found, generating random integer'
                    id_ = random.randint(0, 1000)
                self.parse_representation(base_url, bandwidth, id_,
                                          child_element)
        base_url.adaption_set = ''

    def parse_representation(self, base_url, bandwidth, id_, parent_element):
        """Parse 'representation' level XML."""
        for child_element in parent_element:
            if 'SegmentBase' in child_element.tag:
                self.parse_segment_base(base_url, child_element)
            if 'BaseURL' in child_element.tag:
                base_url.representation = child_element.text
            if 'SegmentList' in child_element.tag:
                duration = int(child_element.attrib['duration'])
                self._max_duration(duration)
                self.parse_segment_list(base_url=base_url,
                                        duration=duration,
                                        bandwidth=bandwidth,
                                        id_=id_,
                                        parent_element=child_element)
        base_url.representation = ''

    def _max_duration(self, duration):
        if duration > self.max_duration:
            self.max_duration = duration

    def parse_segment_base(self, base_url, parent_element):
        """
        Parse 'segment_base' level XML.

        Should be initialisation URLs.

        """
        for child_element in parent_element:
            if 'Initialization' in child_element.tag:
                try:
                    media_range = child_element.attrib['range'].split('-')
                except KeyError:
                    media_range = (0, 0)
                self.initialisations.append((None, base_url.resolve() +
                                            child_element.attrib['sourceURL'],
                                            int(media_range[0]),
                                            int(media_range[1])))

    def parse_segment_list(self, **kwargs):
        """
        Parse 'segment_list' level XML.

        Should be source URLs, describing actual content.

        """
        queue = Queue.Queue()
        for child_element in kwargs['parent_element']:
            if 'SegmentURL' in child_element.tag:
                try:
                    media_range = child_element.attrib['mediaRange'] \
                        .split('-')
                except KeyError:
                    media_range = (0, 0)
                queue.put((kwargs['duration'],
                           kwargs['base_url'].resolve() +
                           child_element.attrib['media'], int(media_range[0]),
                           int(media_range[1]), int(kwargs['bandwidth']),
                           int(kwargs['id_'])))
        self.representations.append({'bandwidth': kwargs['bandwidth'],
                                     'queue': queue})

    def initialise(self):
        """Download necessary initialisation files."""
        self.player.event('start', 'downloading initializations')
        total_duration = 0
        total_length = 0
        for item in self.initialisations:
            duration, length = self.player.fetch_item(item)
            total_duration += duration
            total_length += length
        self.player.update_bandwidth(total_duration, total_length)
        self.player.event('stop ', 'downloading initializations')

    def candidate(self, bandwidth):
        """
        Select the playback candidate that best matches current bandwidth
        availability.

        """
        # TODO: account for none aligned segments
        candidate_index = self.bandwidth_match(bandwidth)
        candidate = None
        for representation in self.representations:
            if representation is self.representations[candidate_index]:
                candidate = representation['queue'].get()
            else:
                representation['queue'].get()
        if candidate is None:
            raise Queue.Empty
        return candidate

    def bandwidth_match(self, bandwidth):
        candidate_index = min(range(len(self.representations)), key=lambda
                              i: abs(self.representations[i]['bandwidth'] -
                              int(bandwidth)))
        return candidate_index

    class BaseURL(object):
        """
        Object used to resolve the current level of base URL.

        This is used as a prefix on the source URL if found.

        """

        representation = None
        adaption_set = None
        period = None
        mpd = None

        def __init__(self):
            """Initialise base URL object by clearing all values."""
            self.clear()

        def clear(self):
            """Clear all values with an empty string."""
            self.representation = ''
            self.adaption_set = ''
            self.period = ''
            self.mpd = ''

        def resolve(self):
            """Return the correct base URL."""
            if self.representation != str(''):
                return self.representation
            elif self.adaption_set != str(''):
                return self.adaption_set
            elif self.period != str(''):
                return self.period
            elif self.mpd != str(''):
                return self.mpd
            else:
                return str('')