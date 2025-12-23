package com.example.news.controller;

import com.example.news.dto.NewsEntryRequest;
import com.example.news.dto.NewsEntryResponse;
import com.example.news.service.NewsEntryService;
import jakarta.validation.Valid;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDate;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/entries")
public class NewsEntryController {

    private final NewsEntryService newsEntryService;

    public NewsEntryController(NewsEntryService newsEntryService) {
        this.newsEntryService = newsEntryService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public NewsEntryResponse create(@Valid @RequestBody NewsEntryRequest request) {
        return newsEntryService.create(request);
    }

    @GetMapping
    public List<NewsEntryResponse> list(@RequestParam(value = "from", required = false)
                                        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate from,
                                        @RequestParam(value = "to", required = false)
                                        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate to,
                                        @RequestParam(value = "q", required = false) String q,
                                        @RequestParam(value = "hashtag", required = false) String hashtag,
                                        @RequestParam(value = "hashtags", required = false) String hashtagList) {
        Set<String> tags = new LinkedHashSet<>();
        if (hashtag != null) {
            tags.add(hashtag);
        }
        if (hashtagList != null) {
            for (String part : hashtagList.split(",")) {
                if (!part.isBlank()) {
                    tags.add(part);
                }
            }
        }
        return newsEntryService.list(from, to, q, tags);
    }

    @GetMapping("/{id}")
    public NewsEntryResponse get(@PathVariable UUID id) {
        return newsEntryService.get(id);
    }

    @PutMapping("/{id}")
    public NewsEntryResponse update(@PathVariable UUID id, @Valid @RequestBody NewsEntryRequest request) {
        return newsEntryService.update(id, request);
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable UUID id) {
        newsEntryService.delete(id);
    }
}
