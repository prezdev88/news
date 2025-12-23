import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormArray, FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { NewsService, NewsEntryResponse } from './news.service';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './home.component.html'
})
export class HomeComponent implements OnInit {
  loading = signal(false);
  entries = signal<NewsEntryResponse[]>([]);
  hashtags = signal<string[]>([]);

  entryForm: FormGroup = this.fb.group({
    date: ['', Validators.required],
    headline: ['', Validators.required],
    hashtags: [''],
    sources: this.fb.array([])
  });

  constructor(private fb: FormBuilder, private service: NewsService) {}

  ngOnInit(): void {
    this.loadEntries();
    this.loadHashtags();
    this.addSource();
  }

  get sources(): FormArray {
    return this.entryForm.get('sources') as FormArray;
  }

  addSource(): void {
    this.sources.push(this.fb.group({
      url: ['']
    }));
  }

  removeSource(idx: number): void {
    this.sources.removeAt(idx);
  }

  loadEntries(): void {
    this.loading.set(true);
    this.service.listEntries({}).subscribe({
      next: (entries) => {
        this.entries.set(entries);
        // fallback: derive hashtags from entries in case hashtag API fails
        this.hashtags.set(this.uniqueTags(entries));
        this.loading.set(false);
      },
      error: () => this.loading.set(false)
    });
  }

  loadHashtags(): void {
    this.service.listHashtags().subscribe({
      next: (res) => this.hashtags.set(res.map(h => h.tag)),
      error: () => this.hashtags.set(this.uniqueTags(this.entries()))
    });
  }

  submitEntry(): void {
    if (this.entryForm.invalid) return;
    const raw = this.entryForm.value;
    const payload = {
      date: raw.date,
      headline: raw.headline,
      hashtags: this.parseTags(raw.hashtags || ''),
      sources: (raw.sources || []).filter((s: any) => s.url).map((s: any) => ({
        name: this.hostFromUrl(s.url),
        url: s.url!
      }))
    };
    this.loading.set(true);
    this.service.createEntry(payload).subscribe({
      next: () => {
        this.entryForm.reset();
        this.sources.clear();
        this.addSource();
        this.loadEntries();
        this.loadHashtags();
        this.loading.set(false);
      },
      error: () => this.loading.set(false)
    });
  }

  private parseTags(value: string): string[] {
    return value
      .split(',')
      .map(t => t.trim())
      .filter(t => t.length > 0);
  }

  hostFromUrl(url: string): string {
    if (!url) return '';
    try {
      return new URL(url).host || url;
    } catch {
      return url;
    }
  }

  private uniqueTags(entries: NewsEntryResponse[]): string[] {
    const set = new Set<string>();
    entries.forEach(e => e.hashtags.forEach(t => set.add(t)));
    return Array.from(set).sort();
  }
}
