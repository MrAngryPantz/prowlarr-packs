using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using FluentAssertions;
using Moq;
using NUnit.Framework;
using NzbDrone.Core.Exceptions;
using NzbDrone.Core.Indexers;
using NzbDrone.Core.IndexerSearch;
using NzbDrone.Core.IndexerSearch.Definitions;
using NzbDrone.Core.Parser.Model;
using NzbDrone.Core.Test.Framework;

namespace NzbDrone.Core.Test.IndexerSearchTests
{
    public class PackSearchFixture : CoreTest<ReleaseSearchService>
    {
        private Mock<IIndexer> _indexer;
        private IndexerCapabilities _caps;
        private List<SearchCriteriaBase> _searches;

        [SetUp]
        public void Setup()
        {
            _caps = new IndexerCapabilities();
            _caps.SearchParams.Clear();
            _caps.TvSearchParams.Clear();
            _caps.MovieSearchParams.Clear();
            _caps.Categories.AddCategoryMapping(1, NewznabStandardCategory.TV);
            _caps.Categories.AddCategoryMapping(2, NewznabStandardCategory.Movies);
            _searches = new List<SearchCriteriaBase>();
            _indexer = Mocker.GetMock<IIndexer>();
            _indexer.SetupGet(i => i.Definition).Returns(new IndexerDefinition { Id = 1, Name = "Test indexer" });
            _indexer.Setup(i => i.GetCapabilities()).Returns(_caps);
            _indexer.Setup(i => i.Fetch(It.IsAny<TvSearchCriteria>())).Callback<TvSearchCriteria>(s => _searches.Add(s)).ReturnsAsync(Results);
            _indexer.Setup(i => i.Fetch(It.IsAny<MovieSearchCriteria>())).Callback<MovieSearchCriteria>(s => _searches.Add(s)).ReturnsAsync(Results);
            _indexer.Setup(i => i.Fetch(It.IsAny<BasicSearchCriteria>())).Callback<BasicSearchCriteria>(s => _searches.Add(s)).ReturnsAsync(Results);
            Mocker.GetMock<IIndexerFactory>().Setup(i => i.Enabled(It.IsAny<bool>())).Returns(new List<IIndexer> { _indexer.Object });
        }

        private IndexerPageableQueryResult Results => new IndexerPageableQueryResult
        {
            Releases = new List<ReleaseInfo>
            {
                new TorrentInfo { Guid = "pack", Title = "Example.S01-S03.1080p.WEB-DL", Seeders = 3, Peers = 5, Size = 123456789, DownloadUrl = "https://example.invalid/pack", Categories = new List<IndexerCategory> { NewznabStandardCategory.TV } }
            }
        };

        [TestCase("tvpack", true, typeof(TvSearchCriteria), "tvsearch", 5000)]
        [TestCase("moviepack", true, typeof(MovieSearchCriteria), "movie", 2000)]
        [TestCase("tvpack", false, typeof(BasicSearchCriteria), "search", 5000)]
        [TestCase("moviepack", false, typeof(BasicSearchCriteria), "search", 2000)]
        public async Task should_use_supported_title_search_without_narrow_filters(string type, bool specialized, System.Type expectedType, string expectedSearchType, int category)
        {
            _caps.SearchParams.Add(SearchParam.Q);
            if (specialized)
            {
                _caps.TvSearchParams.Add(TvSearchParam.Q);
                _caps.MovieSearchParams.Add(MovieSearchParam.Q);
            }

            await Subject.Search(new NewznabRequest { t = type, q = " Example ", season = 1, ep = "1", year = 2000, imdbid = "1234567", tmdbid = 12, tvdbid = 34, offset = 100, limit = 50 }, new List<int> { 1 }, true);

            var search = _searches.Should().ContainSingle().Subject;
            search.Should().BeOfType(expectedType);
            search.SearchType.Should().Be(expectedSearchType);
            search.SearchTerm.Should().Be("Example");
            search.Categories.Should().Equal(category);
            search.Offset.Should().Be(100);
            search.Limit.Should().Be(50);
            if (search is TvSearchCriteria tv)
            {
                tv.Season.Should().BeNull();
                tv.Episode.Should().BeNull();
                tv.TvdbId.Should().BeNull();
                tv.ImdbId.Should().BeNull();
                tv.Year.Should().BeNull();
            }

            if (search is MovieSearchCriteria movie)
            {
                movie.ImdbId.Should().BeNull();
                movie.TmdbId.Should().BeNull();
                movie.Year.Should().BeNull();
            }
        }

        [TestCase("tvpack")]
        [TestCase("moviepack")]
        public async Task should_skip_id_only_indexers(string type)
        {
            _caps.TvSearchParams.Add(TvSearchParam.TvdbId);
            _caps.MovieSearchParams.Add(MovieSearchParam.ImdbId);
            var results = await Subject.Search(new NewznabRequest { t = type, q = "Example" }, new List<int> { 1 }, true);
            results.Releases.Should().BeEmpty();
            _searches.Should().BeEmpty();
        }

        [TestCase(null)]
        [TestCase("")]
        [TestCase("  ")]
        [TestCase("Example {Season:1}")]
        [TestCase("{ImdbId:1234567}")]
        public void should_require_plain_title(string title)
        {
            Assert.ThrowsAsync<SearchFailedException>(() => Subject.Search(new NewznabRequest { t = "tvpack", q = title }, new List<int> { 1 }, true));
            _searches.Should().BeEmpty();
        }

        [Test]
        public async Task should_preserve_pack_titles_seeders_and_download_links()
        {
            _caps.SearchParams.Add(SearchParam.Q);
            var results = await Subject.Search(new NewznabRequest { t = "tvpack", q = "Example" }, new List<int> { 1 }, true);
            var pack = results.Releases.Single().Should().BeOfType<TorrentInfo>().Subject;
            pack.Title.Should().Be("Example.S01-S03.1080p.WEB-DL");
            pack.Seeders.Should().Be(3);
            pack.DownloadUrl.Should().Be("https://example.invalid/pack");
            pack.Size.Should().Be(123456789);
        }

        [Test]
        public async Task should_keep_category_and_size_filters()
        {
            _caps.SearchParams.Add(SearchParam.Q);
            var results = await Subject.Search(new NewznabRequest { t = "tvpack", q = "Example", cat = "5000", maxsize = 100 }, new List<int> { 1 }, true);
            results.Releases.Should().BeEmpty();
            _searches.Single().Categories.Should().Equal(5000);
        }

        [Test]
        public async Task should_obey_query_limits()
        {
            _caps.SearchParams.Add(SearchParam.Q);
            Mocker.GetMock<IIndexerLimitService>().Setup(s => s.AtQueryLimit(It.IsAny<IndexerDefinition>())).Returns(true);
            await Subject.Search(new NewznabRequest { t = "tvpack", q = "Example" }, new List<int> { 1 }, true);
            _searches.Should().BeEmpty();
        }

        [Test]
        public async Task should_leave_ordinary_search_filters_intact()
        {
            await Subject.Search(new NewznabRequest { t = "tvsearch", q = "Example", season = 3, ep = "2", tvdbid = 42 }, new List<int> { 1 }, false);
            var tv = _searches.Single().Should().BeOfType<TvSearchCriteria>().Subject;
            tv.Season.Should().Be(3);
            tv.Episode.Should().Be("2");
            tv.TvdbId.Should().Be(42);
        }
    }
}
