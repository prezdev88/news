package com.example.news.web;

import com.example.news.dto.NewsEntryRequest;
import com.example.news.dto.NewsEntrySourceRequest;
import com.example.news.dto.NewsEntryResponse;
import com.example.news.service.HashtagService;
import com.example.news.service.NewsEntryService;
import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

import java.net.URI;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import jakarta.servlet.http.HttpServletRequest;
import java.util.UUID;

@Controller
public class NewsPageController {

    private final NewsEntryService newsEntryService;
    private final HashtagService hashtagService;

    public NewsPageController(NewsEntryService newsEntryService, HashtagService hashtagService) {
        this.newsEntryService = newsEntryService;
        this.hashtagService = hashtagService;
    }

    @GetMapping("/")
    public String home(@RequestParam(value = "created", required = false) String created,
                       HttpServletRequest request,
                       Model model) {
        NewsEntryForm form = new NewsEntryForm();
        ensureSourceRow(form);
        populateHome(model, form);
        model.addAttribute("created", created != null);
        model.addAttribute("activePage", "home");
        model.addAttribute("basePath", resolveBasePath(request));
        return "index";
    }

    @PostMapping("/entries")
    public String create(@Valid @ModelAttribute("entryForm") NewsEntryForm form,
                         BindingResult bindingResult,
                         Model model,
                         RedirectAttributes redirectAttributes,
                         HttpServletRequest request) {
        if (bindingResult.hasErrors()) {
            ensureSourceRow(form);
            populateHome(model, form);
            model.addAttribute("activePage", "home");
            return "index";
        }
        newsEntryService.create(toRequest(form));
        redirectAttributes.addAttribute("created", "1");
        return "redirect:" + resolveBasePath(request);
    }

    @GetMapping({"/filtros", "/filtros/"})
    public String filters(@ModelAttribute("filterForm") FilterForm form,
                          HttpServletRequest request,
                          Model model) {
        List<NewsEntryResponse> entries = newsEntryService.list(
                form.getFrom(),
                form.getTo(),
                form.getQ(),
                parseTags(form.getHashtags())
        );
        model.addAttribute("entries", entries);
        model.addAttribute("activePage", "filters");
        model.addAttribute("basePath", resolveBasePath(request));
        return "filters";
    }

    @GetMapping("/entries/{id}/edit")
    public String edit(@PathVariable("id") UUID id, HttpServletRequest request, Model model) {
        NewsEntryResponse entry = newsEntryService.get(id);
        NewsEntryForm form = toForm(entry);
        ensureSourceRow(form);
        model.addAttribute("entryForm", form);
        model.addAttribute("entryId", id);
        model.addAttribute("activePage", "home");
        model.addAttribute("basePath", resolveBasePath(request));
        return "edit";
    }

    @PostMapping("/entries/{id}/edit")
    public String update(@PathVariable("id") UUID id,
                         @Valid @ModelAttribute("entryForm") NewsEntryForm form,
                         BindingResult bindingResult,
                         HttpServletRequest request,
                         Model model) {
        if (bindingResult.hasErrors()) {
            ensureSourceRow(form);
            model.addAttribute("entryId", id);
            model.addAttribute("activePage", "home");
            model.addAttribute("basePath", resolveBasePath(request));
            return "edit";
        }
        newsEntryService.update(id, toRequest(form));
        return "redirect:" + resolveBasePath(request);
    }

    @PostMapping("/entries/{id}/delete")
    public String delete(@PathVariable("id") UUID id, HttpServletRequest request) {
        newsEntryService.delete(id);
        return "redirect:" + resolveBasePath(request);
    }

    private void populateHome(Model model, NewsEntryForm form) {
        model.addAttribute("entryForm", form);
        model.addAttribute("entries", newsEntryService.list(null, null, null, Set.of()));
        model.addAttribute("hashtags", hashtagService.listHashtags(null).stream()
                .map(h -> h.tag())
                .toList());
    }

    private void ensureSourceRow(NewsEntryForm form) {
        if (form.getSources() == null || form.getSources().isEmpty()) {
            form.setSources(new ArrayList<>());
            form.getSources().add(new NewsEntrySourceForm());
        }
    }

    private NewsEntryRequest toRequest(NewsEntryForm form) {
        List<String> tags = new ArrayList<>(parseTags(form.getHashtags()));
        List<NewsEntrySourceRequest> sources = new ArrayList<>();
        if (form.getSources() != null) {
            for (NewsEntrySourceForm source : form.getSources()) {
                if (source == null || source.getUrl() == null || source.getUrl().isBlank()) {
                    continue;
                }
                String url = source.getUrl().trim();
                sources.add(new NewsEntrySourceRequest(hostFromUrl(url), url));
            }
        }
        LocalDate date = form.getDate();
        return new NewsEntryRequest(date, form.getHeadline(), tags, sources);
    }

    private Set<String> parseTags(String raw) {
        Set<String> tags = new LinkedHashSet<>();
        if (raw == null || raw.isBlank()) {
            return tags;
        }
        for (String part : raw.split(",")) {
            String trimmed = part.trim();
            if (!trimmed.isEmpty()) {
                tags.add(trimmed);
            }
        }
        return tags;
    }

    private String hostFromUrl(String url) {
        try {
            String host = URI.create(url).getHost();
            if (host != null && !host.isBlank()) {
                return host;
            }
        } catch (IllegalArgumentException ignored) {
        }
        return url;
    }

    private NewsEntryForm toForm(NewsEntryResponse entry) {
        NewsEntryForm form = new NewsEntryForm();
        form.setDate(entry.date());
        form.setHeadline(entry.headline());
        form.setHashtags(String.join(",", entry.hashtags()));
        List<NewsEntrySourceForm> sources = new ArrayList<>();
        if (entry.sources() != null) {
            for (var source : entry.sources()) {
                NewsEntrySourceForm src = new NewsEntrySourceForm();
                src.setUrl(source.url());
                sources.add(src);
            }
        }
        form.setSources(sources);
        return form;
    }

    private String resolveBasePath(HttpServletRequest request) {
        String prefix = request.getHeader("X-Forwarded-Prefix");
        if (prefix == null || prefix.isBlank()) {
            return "/";
        }
        if (!prefix.startsWith("/")) {
            prefix = "/" + prefix;
        }
        return prefix.endsWith("/") ? prefix : prefix + "/";
    }
}
