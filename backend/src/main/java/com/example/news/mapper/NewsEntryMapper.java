package com.example.news.mapper;

import com.example.news.domain.Hashtag;
import com.example.news.domain.NewsEntry;
import com.example.news.domain.NewsEntrySource;
import com.example.news.dto.NewsEntryResponse;
import com.example.news.dto.NewsEntrySourceResponse;
import org.springframework.stereotype.Component;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

@Component
public class NewsEntryMapper {

    public NewsEntryResponse toResponse(NewsEntry entry) {
        List<String> tags = entry.getHashtags().stream()
                .map(Hashtag::getTag)
                .sorted()
                .toList();

        List<NewsEntrySourceResponse> sources = entry.getSources().stream()
                // guard against duplicates coming from joins
                .collect(Collectors.toMap(
                        NewsEntrySource::getId,
                        Function.identity(),
                        (a, b) -> a,
                        java.util.LinkedHashMap::new
                ))
                .values()
                .stream()
                .sorted(Comparator.comparing(NewsEntrySource::getCreatedAt))
                .map(this::toSourceResponse)
                .toList();

        return new NewsEntryResponse(
                entry.getId(),
                entry.getDate(),
                entry.getHeadline(),
                tags,
                sources,
                entry.getCreatedAt(),
                entry.getUpdatedAt()
        );
    }

    private NewsEntrySourceResponse toSourceResponse(NewsEntrySource source) {
        return new NewsEntrySourceResponse(
                source.getId(),
                source.getName(),
                source.getUrl()
        );
    }
}
