package com.example.news.controller;

import com.example.news.dto.HashtagResponse;
import com.example.news.service.HashtagService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/v1/hashtags")
public class HashtagController {

    private final HashtagService hashtagService;

    public HashtagController(HashtagService hashtagService) {
        this.hashtagService = hashtagService;
    }

    @GetMapping
    public List<HashtagResponse> list(@RequestParam(value = "q", required = false) String q) {
        return hashtagService.listHashtags(q);
    }

    @GetMapping("/{tag}")
    public HashtagResponse get(@PathVariable("tag") String tag) {
        return hashtagService.getHashtag(tag);
    }
}
