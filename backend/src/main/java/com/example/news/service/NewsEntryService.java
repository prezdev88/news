package com.example.news.service;

import com.example.news.domain.Hashtag;
import com.example.news.domain.NewsEntry;
import com.example.news.domain.NewsEntrySource;
import com.example.news.dto.NewsEntryRequest;
import com.example.news.dto.NewsEntryResponse;
import com.example.news.exception.NotFoundException;
import com.example.news.mapper.NewsEntryMapper;
import com.example.news.repository.NewsEntryRepository;
import com.example.news.spec.NewsEntrySpecifications;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

@Service
public class NewsEntryService {

    private final NewsEntryRepository newsEntryRepository;
    private final HashtagService hashtagService;
    private final HashtagNormalizer hashtagNormalizer;
    private final NewsEntryMapper mapper;

    public NewsEntryService(NewsEntryRepository newsEntryRepository,
                            HashtagService hashtagService,
                            HashtagNormalizer hashtagNormalizer,
                            NewsEntryMapper mapper) {
        this.newsEntryRepository = newsEntryRepository;
        this.hashtagService = hashtagService;
        this.hashtagNormalizer = hashtagNormalizer;
        this.mapper = mapper;
    }

    @Transactional
    public NewsEntryResponse create(NewsEntryRequest request) {
        NewsEntry entry = new NewsEntry();
        applyRequest(entry, request);
        NewsEntry saved = newsEntryRepository.save(entry);
        return mapper.toResponse(saved);
    }

    @Transactional(readOnly = true)
    public List<NewsEntryResponse> list(java.time.LocalDate from,
                                        java.time.LocalDate to,
                                        String q,
                                        Set<String> hashtags) {
        Set<String> normalized = hashtags == null ? Set.of() : hashtagNormalizer.normalizeMany(hashtags);
        var spec = NewsEntrySpecifications.withFilters(from, to, q, normalized);
        Sort sort = Sort.by(Sort.Order.asc("date"), Sort.Order.asc("createdAt"));
        return newsEntryRepository.findAll(spec, sort).stream()
                .map(mapper::toResponse)
                .collect(Collectors.toList());
    }

    @Transactional(readOnly = true)
    public NewsEntryResponse get(UUID id) {
        NewsEntry entry = newsEntryRepository.findWithDetailsById(id)
                .orElseThrow(() -> new NotFoundException("Entrada no encontrada"));
        return mapper.toResponse(entry);
    }

    @Transactional
    public NewsEntryResponse update(UUID id, NewsEntryRequest request) {
        NewsEntry entry = newsEntryRepository.findWithDetailsById(id)
                .orElseThrow(() -> new NotFoundException("Entrada no encontrada"));
        applyRequest(entry, request);
        return mapper.toResponse(newsEntryRepository.save(entry));
    }

    @Transactional
    public void delete(UUID id) {
        NewsEntry entry = newsEntryRepository.findWithDetailsById(id)
                .orElseThrow(() -> new NotFoundException("Entrada no encontrada"));
        newsEntryRepository.delete(entry);
    }

    private void applyRequest(NewsEntry entry, NewsEntryRequest request) {
        entry.setDate(request.date());
        entry.setHeadline(request.headline());

        Set<String> rawTags = request.hashtags() == null ? Set.of() : new HashSet<>(request.hashtags());
        List<Hashtag> hashtags = hashtagService.findOrCreate(rawTags);
        entry.setHashtags(new HashSet<>(hashtags));

        entry.getSources().clear();
        if (request.sources() != null) {
            for (var src : request.sources()) {
                NewsEntrySource source = new NewsEntrySource();
                source.setEntry(entry);
                source.setName(src.name());
                source.setUrl(src.url());
                entry.getSources().add(source);
            }
        }
    }
}
