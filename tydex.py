"""
2022-06-13
John Robinson
Sumitomo Rubber USA, LLC

Reads TYDEX files into a Python data class.

Python 3.7+ (dataclasses)
"""
from dataclasses import dataclass, field
import os
import re

import numpy as np

TOLERANCE = {
    'FZW': 100,         # [N]
    'SLIPANGL': 0.25,   # [deg]
    'INCLANGL': 1.6,    # [deg]
    'INFLPRES': 1000,   # [pa]
}


@dataclass
class TydexData:
    """
    Reads in and processes a Tydex data file
    """
    tydex_file_name: str
    tydex_file_str: str = None
    keywords: list = field(default_factory=list)
    headers: dict = field(default_factory=dict)
    comments: list = field(default_factory=list)
    constants: dict = field(default_factory=dict)
    channels: list = field(default_factory=list)
    data: dict = field(default_factory=dict)

    def __post_init__(self):
        self.read_tydex_file()

    def __str__(self):
        return self.comments

    def __repr__(self):
        return ' '.join([str(item) for item in self.comments])

    def get_keyword_string(self, keyword: str) -> str:
        """
        For a given 'tydex_str' and 'keyword' (ex: **HEADER), return all the string data for that keyword (before the next
        **KEYWORD begins)

        :param keyword:
        :return:
        """
        kywrd_header_string = f'**{keyword}\n'
        start_idx = self.tydex_file_str.find(kywrd_header_string)
        end_idx_delta = self.tydex_file_str[start_idx + 2:].find('**')
        kywrd_string = self.tydex_file_str[start_idx+len(kywrd_header_string):start_idx + end_idx_delta]

        return kywrd_string

    def parse_header_lines(self) -> dict:
        """
        Parses the tydex **HEADER lines and returns a dictionary
        :param tydex_file_str:
        :return:
        """
        kywrd = 'HEADER'
        kywrd_string = self.get_keyword_string(kywrd)
        headers = {}
        for ln in kywrd_string.splitlines():
            ky = ln[0:10]
            val = ln[50:]
            headers[ky.strip()] = val

        self.headers = headers
        return self.headers

    def parse_comments(self) -> list:
        """
        Reads in the comments in a tydex file

        :param tydex_file_str:
        :return:
        """
        kywrd_string = self.get_keyword_string('COMMENTS')

        self.comments = kywrd_string.splitlines()
        return self.comments

    def parse_constants(self) -> dict:
        """
        Parses tydex **CONSTANTS lines and returns a dictionary
        """
        kywrd = 'CONSTANTS'
        kywrd_string = self.get_keyword_string(kywrd)
        constants = {}
        for ln in kywrd_string.splitlines():
            ky = ln[0:10].strip()
            desc = ln[11:40]
            units = ln[41:49]
            val = ln[50:]

            if 'NUM' in ky:
                try:
                    val = int(val)
                except ValueError:
                    # If trying to parse a non-int as an int, just pass
                    pass
            else:
                try:
                    val = float(val)
                except ValueError:
                    # Try to parse as float, if not then its a string
                    pass

            constants[ky] = val

        self.constants = constants
        return self.constants

    def parse_channel_names(self) -> list:
        """
        Parse the channel names for the tydex files
        """
        kywrd = 'MEASURCHANNELS'
        kywrd_string = self.get_keyword_string(kywrd)
        measure_channels = []
        for ln in kywrd_string.splitlines():
            ky = ln[0:10].strip()

            if ky.startswith('**'):
                pass
            else:
                desc = ln[10:39].strip()
                units = ln[40:50].strip()
                val = ln[50:]
                measure_channels.append(
                    {
                        'name': ky,
                        'description': desc,
                        'units': units,
                    }
                )

        self.channels = measure_channels
        return self.channels

    def parse_measured_data(self) -> dict:
        """
        Reads the Tydex data file in and returns a Pandas DataFrame
        """
        kywrd = 'MEASURDATA'
        kywrd_string = self.get_keyword_string(kywrd)
        data = {}
        for ln in kywrd_string.splitlines():
            dta_ln = [float(val) for val in ln.split()]
            for ii, channel in enumerate(self.channels):
                try:
                    data[channel['name']].append(dta_ln[ii])
                except KeyError:
                    data[channel['name']] = []
                    data[channel['name']].append(dta_ln[ii])

        self.data = data
        return data

    def read_tydex_file(self):
        with open(self.tydex_file_name, 'r') as f:
            self.tydex_file_str = f.read()

        self.keywords = re.findall('\*\*([A-Z]+)\n', self.tydex_file_str)
        headers = self.parse_header_lines()
        comments = self.parse_comments()
        constants = self.parse_constants()
        channels = self.parse_channel_names()
        data = self.parse_measured_data()

    def average_difference_between_constant_and_data(self, key: str) -> float:
        """
        Calculates the average difference between a tydex's specified value in 'CONSTANTS' and the
        actual measured values. Used for error checking tydex data files.

        :param key:
        :return:
        """
        try:
            average_delta = np.average(np.array(self.data[key]) - self.constants[key])
            # if np.abs(self.constants[key]) < 0.5:
            #     # If value less than 0.5, use absolute error
            #     average_delta_pct = np.abs(average_delta)
            # else:
            #     average_delta_pct = np.abs(average_delta / self.constants[key] * 100)

        except KeyError:
            print(f"No {key} in constants")
            return 0

        return average_delta, TOLERANCE[key]

    def verify_constants(self):
        """
        This will check the constants in a Tydex run-file and verify that the data is on average
        "close" to the specified constant value
        :return:
        """
        channel_names = [itm['name'] for itm in self.channels]
        constant_names = self.constants.keys()
        overlapping_keys = [ky for ky in constant_names if ky in channel_names]

        for key in overlapping_keys:
            average_delta_pct, tolerance = self.average_difference_between_constant_and_data(key)
            if average_delta_pct > tolerance:
                fname = os.path.basename(self.tydex_file_name)
                # raise(
                print(
                    f"{fname}: {key:10} does not match within {tolerance} "
                    f"(err={average_delta_pct:.1f}), nominal = {self.constants[key]}"
                )


if __name__ == "__main__":
    import glob
    root_file_dir = "tydex/*/Run*"
    tydex_file_names = glob.glob(root_file_dir + '/*.tdx')
    for tydex_file_name in tydex_file_names:
        tydex_data = TydexData(tydex_file_name=tydex_file_name)
        try:
            tydex_data.verify_constants()
        except ValueError as err:
            print(err)

