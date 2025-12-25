package com.example.news.web;

import jakarta.validation.constraints.Size;

public class NewsEntrySourceForm {

    @Size(max = 1024)
    private String url;

    public String getUrl() {
        return url;
    }

    public void setUrl(String url) {
        this.url = url;
    }
}
