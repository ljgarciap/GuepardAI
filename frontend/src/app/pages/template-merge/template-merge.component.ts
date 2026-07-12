import { Component, inject, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { Subject, Subscription, interval } from 'rxjs';
import { debounceTime, distinctUntilChanged, switchMap, takeWhile } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import { triggerBlobDownload } from '../../utils/download.util';
import { BrandService, PromptMetadata, TemplateMergeHistoryItem } from '../../services/brand.service';
import { PromptSupportComponent } from '../../components/prompt-support/prompt-support.component';

interface TemplateAsset {
  id: number;
  filename: string;
  description: string;
  brand_id: number | null;
  created_at: string;
}

interface MergeSummary {
  rewritten: number;
  adapted: number;
  preserved: number;
  unfilled: number;
  kept_original: number;
  failed: number;
}

interface VisualQaFinding {
  type: 'overflow' | 'contrast' | 'overlap';
  severity: 'high' | 'medium' | 'low';
  detail: string;
}

interface VisualQaReport {
  status: 'ok' | 'unavailable' | 'failed';
  total_findings?: number;
  slides_reviewed?: number;
  slides?: { slide: number; findings: VisualQaFinding[] }[];
  detail?: string;
}

interface MergeJobStatus {
  job_id: number;
  status: string;
  progress: number;
  current_step: string;
  error_detail: string | null;
  output_url: string | null;
  display_name: string | null;
  merge_summary?: MergeSummary | null;
  merge_report?: { visual_qa?: VisualQaReport } | null;
}

@Component({
  selector: 'app-template-merge',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, PromptSupportComponent],
  templateUrl: './template-merge.component.html',
  styleUrl: './template-merge.component.css'
})
export class TemplateMergeComponent implements OnInit, OnDestroy {
  private http = inject(HttpClient);
  private brandService = inject(BrandService);

  // ── Form state ──────────────────────────────────────────────────────────────
  brands: any[] = [];
  selectedBrandId: number | null = null;
  selectedTemplateId: number | null = null;
  selectedKnowledge: string = '';
  prompt: string = '';
  // No se envía a TemplateMergeRequest (ese pipeline no lo consume) — solo se
  // guarda para que "Save as favorite" pueda incluir la selección estructurada.
  promptMetadata: PromptMetadata | null = null;
  displayName: string = '';

  // ── Upload state ─────────────────────────────────────────────────────────
  uploadFile: File | null = null;
  uploadFileName: string = '';
  isUploading = false;
  uploadError: string = '';

  // ── Data ─────────────────────────────────────────────────────────────────
  templates: TemplateAsset[] = [];
  availableKnowledge: string[] = [];

  // ── Job state ─────────────────────────────────────────────────────────────
  activeJob: MergeJobStatus | null = null;
  completedJobs: MergeJobStatus[] = [];
  isSubmitting = false;
  submitError: string = '';
  private pollSub: Subscription | null = null;

  // ── History tab state ────────────────────────────────────────────────────
  activeView: 'session' | 'history' = 'session';
  historyItems: TemplateMergeHistoryItem[] = [];
  historySearch = '';
  historyDateFrom = '';
  historyDateTo = '';
  historyPage = 1;
  historyPageSize = 12;
  historyTotal = 0;
  renamingHistoryId: number | null = null;
  renameValue = '';
  deleteTarget: TemplateMergeHistoryItem | null = null;
  showDeleteModal = false;
  private historySearch$ = new Subject<string>();
  private historySearchSub?: Subscription;

  ngOnInit(): void {
    this.loadBrands();
    this.loadTemplates();
    this.loadKnowledgeSources();
    this.historySearchSub = this.historySearch$
      .pipe(debounceTime(300), distinctUntilChanged())
      .subscribe(() => {
        this.historyPage = 1;
        this.loadHistory();
      });
  }

  ngOnDestroy(): void {
    this.pollSub?.unsubscribe();
    this.historySearchSub?.unsubscribe();
  }

  // ── Data loading ─────────────────────────────────────────────────────────

  loadBrands(): void {
    this.brandService.getBrands().subscribe({
      next: (res: any[]) => {
        this.brands = res.filter((b: any) => b.id !== -1);
        if (this.brands.length === 1) this.selectedBrandId = this.brands[0].id;
      },
      error: () => this.brands = [],
    });
  }

  onPromptSupportApply(event: { text: string; metadata: PromptMetadata | null }): void {
    this.prompt = event.text;
    this.promptMetadata = event.metadata;
  }

  loadTemplates(): void {
    this.http.get<TemplateAsset[]>(`${environment.apiUrl}/template-merge/templates`)
      .subscribe({
        next: (data) => this.templates = data,
        error: () => this.templates = [],
      });
  }

  loadKnowledgeSources(): void {
    // brand_id=-1 → superuser visibility (same as Synthesis Studio default)
    this.http.get<any>(`${environment.apiUrl}/available-knowledge?brand_id=-1`)
      .subscribe({
        next: (data) => this.availableKnowledge = data?.sources || [],
        error: () => this.availableKnowledge = [],
      });
  }

  // ── Template upload ───────────────────────────────────────────────────────

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files?.length) {
      const file = input.files[0];
      if (!file.name.toLowerCase().endsWith('.pptx')) {
        this.uploadError = 'Only .pptx files are accepted as templates.';
        return;
      }
      this.uploadFile = file;
      this.uploadFileName = file.name;
      this.uploadError = '';
    }
  }

  uploadTemplate(): void {
    if (!this.uploadFile) return;
    this.isUploading = true;
    this.uploadError = '';

    const form = new FormData();
    form.append('file', this.uploadFile);

    this.http.post<any>(`${environment.apiUrl}/template-merge/upload-template`, form)
      .subscribe({
        next: (res) => {
          this.isUploading = false;
          this.uploadFile = null;
          this.uploadFileName = '';
          // Reload templates list, then select the newly uploaded one
          this.http.get<TemplateAsset[]>(`${environment.apiUrl}/template-merge/templates`)
            .subscribe({
              next: (data) => {
                this.templates = data;
                this.selectedTemplateId = res.asset_id;
              },
              error: () => {
                this.selectedTemplateId = res.asset_id;
              }
            });
        },
        error: (err) => {
          this.isUploading = false;
          this.uploadError = err?.error?.detail || 'Upload failed.';
        },
      });
  }

  // ── Job submission ────────────────────────────────────────────────────────

  get canSubmit(): boolean {
    return !!(
      this.selectedBrandId &&
      this.selectedTemplateId &&
      this.selectedKnowledge &&
      this.prompt.trim() &&
      !this.isSubmitting &&
      (!this.activeJob || ['completed', 'error'].includes(this.activeJob.status))
    );
  }

  submit(): void {
    if (!this.canSubmit) return;
    this.isSubmitting = true;
    this.submitError = '';

    const payload = {
      template_asset_id: this.selectedTemplateId,
      knowledge_filename: this.selectedKnowledge,
      prompt: this.prompt.trim(),
      display_name: this.displayName.trim() || null,
      brand_id: this.selectedBrandId,
    };

    this.http.post<any>(`${environment.apiUrl}/template-merge/jobs`, payload)
      .subscribe({
        next: (res) => {
          this.isSubmitting = false;
          this.activeJob = {
            job_id: res.job_id,
            status: 'pending',
            progress: 0,
            current_step: 'Queued...',
            error_detail: null,
            output_url: null,
            display_name: this.displayName || null,
          };
          this.startPolling(res.job_id);
        },
        error: (err) => {
          this.isSubmitting = false;
          this.submitError = err?.error?.detail || 'Failed to create job.';
        },
      });
  }

  // ── Polling ───────────────────────────────────────────────────────────────

  private startPolling(jobId: number): void {
    this.pollSub?.unsubscribe();
    this.pollSub = interval(2500)
      .pipe(
        switchMap(() =>
          this.http.get<MergeJobStatus>(`${environment.apiUrl}/template-merge/jobs/${jobId}`)
        ),
        takeWhile((job) => !['completed', 'error'].includes(job.status), true)
      )
      .subscribe({
        next: (job) => {
          this.activeJob = job;
          if (job.status === 'completed') {
            this.completedJobs.unshift(job);
            if (this.activeView === 'history') this.loadHistory();
          }
        },
        error: () => {},
      });
  }

  // ── Download ──────────────────────────────────────────────────────────────

  private downloadJobFile(jobId: number, filename: string): void {
    this.http.get(`${environment.apiUrl}/template-merge/jobs/${jobId}/download`, { responseType: 'blob' })
      .subscribe({
        next: (blob) => triggerBlobDownload(blob, filename),
        error: () => { this.submitError = 'Download failed. Please try again.'; }
      });
  }

  downloadResult(job: MergeJobStatus): void {
    this.downloadJobFile(job.job_id, `${job.display_name || 'merge_' + job.job_id}.pptx`);
  }

  downloadHistoryItem(item: TemplateMergeHistoryItem): void {
    this.downloadJobFile(item.id, item.filename);
  }

  // ── History tab ───────────────────────────────────────────────────────────

  setView(view: 'session' | 'history'): void {
    this.activeView = view;
    if (view === 'history') this.loadHistory();
  }

  loadHistory(): void {
    this.brandService.getTemplateMergeHistory(undefined, {
      search: this.historySearch,
      dateFrom: this.historyDateFrom || undefined,
      dateTo: this.historyDateTo || undefined,
      page: this.historyPage,
      pageSize: this.historyPageSize,
    }).subscribe({
      next: (res) => {
        this.historyItems = res.items;
        this.historyTotal = res.total;
        this.historyPage = res.page;
      },
      error: () => {},
    });
  }

  onHistorySearchChange(value: string): void {
    this.historySearch$.next(value);
  }

  onHistoryDateChange(): void {
    this.historyPage = 1;
    this.loadHistory();
  }

  clearHistoryFilters(): void {
    this.historySearch = '';
    this.historyDateFrom = '';
    this.historyDateTo = '';
    this.historyPage = 1;
    this.loadHistory();
  }

  get historyTotalPages(): number {
    return Math.max(1, Math.ceil(this.historyTotal / this.historyPageSize));
  }

  goToHistoryPage(page: number): void {
    if (page < 1 || page > this.historyTotalPages || page === this.historyPage) return;
    this.historyPage = page;
    this.loadHistory();
  }

  startHistoryRename(item: TemplateMergeHistoryItem): void {
    this.renamingHistoryId = item.id;
    this.renameValue = item.display_name;
  }

  cancelHistoryRename(): void {
    this.renamingHistoryId = null;
    this.renameValue = '';
  }

  confirmHistoryRename(): void {
    const name = this.renameValue.trim();
    if (!this.renamingHistoryId || !name || name.length > 120) return;

    this.brandService.renameTemplateMergeJob(this.renamingHistoryId, name).subscribe({
      next: (res) => {
        const item = this.historyItems.find(i => i.id === res.id);
        if (item) item.display_name = res.display_name;
        this.cancelHistoryRename();
      },
      error: () => {
        this.cancelHistoryRename();
        this.loadHistory();
      },
    });
  }

  askDeleteHistoryItem(item: TemplateMergeHistoryItem): void {
    this.deleteTarget = item;
    this.showDeleteModal = true;
  }

  cancelDeleteHistoryItem(): void {
    this.deleteTarget = null;
    this.showDeleteModal = false;
  }

  confirmDeleteHistoryItem(): void {
    if (!this.deleteTarget) return;
    const targetId = this.deleteTarget.id;

    this.brandService.deleteTemplateMergeJob(targetId).subscribe({
      next: () => {
        this.cancelDeleteHistoryItem();
        if (this.historyItems.length === 1 && this.historyPage > 1) {
          this.historyPage--;
        }
        this.loadHistory();
      },
      error: () => {
        this.cancelDeleteHistoryItem();
        this.loadHistory();
      },
    });
  }

  // ── UI helpers ────────────────────────────────────────────────────────────

  get progressWidth(): string {
    return `${this.activeJob?.progress ?? 0}%`;
  }

  get isProcessing(): boolean {
    return !!this.activeJob && ['pending', 'processing'].includes(this.activeJob.status);
  }

  get mergeSummary(): MergeSummary | null {
    return this.activeJob?.merge_summary ?? null;
  }

  /** Slots that ended without new content (unfilled) or errored (failed) — worth a review. */
  get mergeWarningCount(): number {
    const s = this.mergeSummary;
    return s ? s.unfilled + s.failed : 0;
  }

  get mergeReplacedCount(): number {
    const s = this.mergeSummary;
    return s ? s.rewritten + s.adapted : 0;
  }

  /** Visual QA report when the pass ran successfully (gate is off by default). */
  get visualQa(): VisualQaReport | null {
    const vqa = this.activeJob?.merge_report?.visual_qa;
    return vqa && vqa.status === 'ok' ? vqa : null;
  }

  get visualQaFindingCount(): number {
    return this.visualQa?.total_findings ?? 0;
  }

  /** Flattened findings with their slide number, for the detail list. */
  get visualQaFindings(): ({ slide: number } & VisualQaFinding)[] {
    const slides = this.visualQa?.slides ?? [];
    return slides.flatMap(s => s.findings.map(f => ({ slide: s.slide, ...f })));
  }

  resetForm(): void {
    this.activeJob = null;
    this.submitError = '';
  }
}
