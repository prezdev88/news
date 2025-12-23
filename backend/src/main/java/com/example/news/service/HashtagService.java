package com.example.news.service;

import com.example.news.domain.Hashtag;
import com.example.news.dto.HashtagResponse;
import com.example.news.exception.NotFoundException;
import com.example.news.repository.HashtagRepository;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

@Service
public class HashtagService {

    private final HashtagRepository hashtagRepository;
    private final HashtagNormalizer normalizer;

    public HashtagService(HashtagRepository hashtagRepository, HashtagNormalizer normalizer) {
        this.hashtagRepository = hashtagRepository;
        this.normalizer = normalizer;
    }

    public List<Hashtag> findOrCreate(Set<String> rawTags) {
        Set<String> tags = normalizer.normalizeMany(rawTags);
        if (tags.isEmpty()) {
            return List.of();
        }
        List<Hashtag> existing = hashtagRepository.findByTagIn(tags);
        Map<String, Hashtag> byTag = new HashMap<>();
        existing.forEach(h -> byTag.put(h.getTag(), h));

        List<Hashtag> toCreate = new ArrayList<>();
        for (String tag : tags) {
            if (!byTag.containsKey(tag)) {
                Hashtag h = new Hashtag();
                h.setTag(tag);
                toCreate.add(h);
                byTag.put(tag, h);
            }
        }
        if (!toCreate.isEmpty()) {
            hashtagRepository.saveAll(toCreate);
        }
        return new ArrayList<>(byTag.values());
    }

    public List<HashtagResponse> listHashtags(String prefix) {
        List<Hashtag> hashtags;
        if (prefix != null && !prefix.isBlank()) {
            String prepared = sanitizePrefix(prefix);
            hashtags = hashtagRepository.findByTagStartingWithIgnoreCaseOrderByTagAsc(prepared);
        } else {
            hashtags = hashtagRepository.findAllByOrderByTagAsc();
        }
        return hashtags.stream()
                .map(this::toResponse)
                .collect(Collectors.toList());
    }

    public HashtagResponse getHashtag(String tag) {
        String normalized = normalizer.normalize(tag);
        Hashtag hashtag = hashtagRepository.findByTag(normalized)
                .orElseThrow(() -> new NotFoundException("Hashtag no encontrado"));
        long count = hashtagRepository.countEntriesWithTag(normalized);
        return new HashtagResponse(hashtag.getTag(), count, hashtag.getCreatedAt());
    }

    private HashtagResponse toResponse(Hashtag hashtag) {
        long count = hashtagRepository.countEntriesWithTag(hashtag.getTag());
        return new HashtagResponse(hashtag.getTag(), count, hashtag.getCreatedAt());
    }

    private String sanitizePrefix(String prefix) {
        String cleaned = prefix.trim();
        while (cleaned.startsWith("#")) {
            cleaned = cleaned.substring(1);
        }
        cleaned = cleaned.toLowerCase();
        cleaned = cleaned.replaceAll("\\s+", "");
        return cleaned;
    }
}
