import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { NewsService, NewsEntryResponse } from './news.service';

@Component({
  selector: 'app-filters',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './filters.component.html'
})
export class FiltersComponent {
  entries: NewsEntryResponse[] = [];
  loading = false;

  filterForm = this.fb.group({
    from: [''],
    to: [''],
    q: [''],
    hashtags: ['']
  });

  constructor(private fb: FormBuilder, private service: NewsService) {}

  applyFilters(): void {
    const { from, to, q, hashtags } = this.filterForm.value;
    const parsedTags = this.parseTags(hashtags || '');
    this.loading = true;
    this.service.listEntries({ from: from || undefined, to: to || undefined, q: q || undefined, hashtags: parsedTags })
      .subscribe({
        next: (res) => {
          this.entries = res;
          this.loading = false;
        },
        error: () => this.loading = false
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
}
