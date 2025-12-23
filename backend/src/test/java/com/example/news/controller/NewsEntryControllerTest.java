package com.example.news.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class NewsEntryControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void createAndFilterByHashtag() throws Exception {
        Map<String, Object> request = Map.of(
                "date", "2024-01-01",
                "headline", "Headline",
                "hashtags", List.of("Kast", "venezuela"),
                "sources", List.of(Map.of("name", "Source A", "url", "https://example.com"))
        );

        MvcResult result = mockMvc.perform(post("/api/v1/entries")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.hashtags[0]").value("kast"))
                .andReturn();

        Map<?, ?> created = objectMapper.readValue(result.getResponse().getContentAsString(), Map.class);
        assertThat(created.get("id")).isNotNull();

        mockMvc.perform(get("/api/v1/entries").param("hashtag", "kast"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].hashtags[0]").value("kast"));
    }
}
