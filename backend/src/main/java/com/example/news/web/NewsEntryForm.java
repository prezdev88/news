package com.example.news.web;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;

public class NewsEntryForm {

    @NotNull
    private LocalDate date;

    @NotBlank
    @Size(max = 500)
    private String headline;

    private String hashtags;

    private List<NewsEntrySourceForm> sources = new ArrayList<>();

    public LocalDate getDate() {
        return date;
    }

    public void setDate(LocalDate date) {
        this.date = date;
    }

    public String getHeadline() {
        return headline;
    }

    public void setHeadline(String headline) {
        this.headline = headline;
    }

    public String getHashtags() {
        return hashtags;
    }

    public void setHashtags(String hashtags) {
        this.hashtags = hashtags;
    }

    public List<NewsEntrySourceForm> getSources() {
        return sources;
    }

    public void setSources(List<NewsEntrySourceForm> sources) {
        this.sources = sources;
    }
}
