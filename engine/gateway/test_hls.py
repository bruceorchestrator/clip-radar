import unittest

from hls import parse, segments_for

MEDIA = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:10
#EXTINF:10.000,
0.ts
#EXTINF:10.000,
1.ts
#EXTINF:10.000,
2-muted.ts
#EXTINF:4.500,
3.ts
#EXT-X-ENDLIST
"""

MASTER = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=6000000,RESOLUTION=1920x1080
1080p60/index-dvr.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=3000000,RESOLUTION=1280x720
720p60/index-dvr.m3u8
"""

FMP4 = """#EXTM3U
#EXT-X-MAP:URI="init.mp4"
#EXTINF:6.0,
seg1.m4s
#EXTINF:6.0,
seg2.m4s
"""


class TestParse(unittest.TestCase):
    def test_media_playlist_times_and_absolute_uris(self):
        pl = parse(MEDIA, "https://cdn.example/vod/chunked/index-dvr.m3u8")
        self.assertEqual([s.start for s in pl.segments], [0.0, 10.0, 20.0, 30.0])
        self.assertEqual(pl.segments[2].uri, "https://cdn.example/vod/chunked/2-muted.ts")
        self.assertIsNone(pl.init_uri)
        self.assertEqual(pl.variants, [])

    def test_master_playlist_lists_variants(self):
        pl = parse(MASTER, "https://cdn.example/vod/master.m3u8")
        self.assertEqual(pl.segments, [])
        self.assertEqual(pl.variants[0], "https://cdn.example/vod/1080p60/index-dvr.m3u8")

    def test_fmp4_init_segment(self):
        pl = parse(FMP4, "https://cdn.example/a/b.m3u8")
        self.assertEqual(pl.init_uri, "https://cdn.example/a/init.mp4")
        self.assertEqual(len(pl.segments), 2)


class TestSegmentsFor(unittest.TestCase):
    pl = parse(MEDIA, "https://cdn.example/x/index.m3u8")

    def test_only_overlapping_segments(self):
        self.assertEqual([s.uri.rsplit("/", 1)[1] for s in segments_for(self.pl, 13, 17)], ["1.ts"])

    def test_edges_pull_in_neighbours(self):
        uris = [s.uri.rsplit("/", 1)[1] for s in segments_for(self.pl, 9, 21)]
        self.assertEqual(uris, ["0.ts", "1.ts", "2-muted.ts"])

    def test_outside_gives_nothing(self):
        self.assertEqual(segments_for(self.pl, 100, 120), [])


if __name__ == "__main__":
    unittest.main()
