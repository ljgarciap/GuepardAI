import { Component, inject, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { interval, Subscription } from 'rxjs';
import { switchMap, takeWhile } from 'rxjs/operators';
import { environment } from '../../../environments/environment';

interface TemplateAsset {
  id: number;
  filename: string;
  description: string;
  brand_id: number | null;
  created_at: string;
}

interface MergeJobStatus {
  job_id: number;
  status: string;
  progress: number;
  current_step: string;
  error_detail: string | null;
  output_url: string | null;
  display_name: string | null;
}

@Component({
  selector: 'app-template-merge',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './template-merge.component.html',
  styleUrl: './template-merge.component.css'
})
export class TemplateMergeComponent implements OnInit, OnDestroy {
  private http = inject(HttpClient);

  // ── Form state ──────────────────────────────────────────────────────────────
  selectedTemplateId: number | null = null;
  selectedKnowledge: string = '';
  prompt: string = '';
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

  ngOnInit(): void {
    this.loadTemplates();
    this.loadKnowledgeSources();
  }

  ngOnDestroy(): void {
    this.pollSub?.unsubscribe();
  }

  // ── Data loading ─────────────────────────────────────────────────────────

  loadTemplates(): void {
    this.http.get<TemplateAsset[]>(`${environment.apiUrl}/api/template-merge/templates`)
      .subscribe({
        next: (data) => this.templates = data,
        error: () => this.templates = [],
      });
  }

  loadKnowledgeSources(): void {
    this.http.get<string[]>(`${environment.apiUrl}/api/available-knowledge`)
      .subscribe({
        next: (data) => this.availableKnowledge = Array.isArray(data) ? data : [],
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

    this.http.post<any>(`${environment.apiUrl}/api/template-merge/upload-template`, form)
      .subscribe({
        next: (res) => {
          this.isUploading = false;
          this.uploadFile = null;
          this.uploadFileName = '';
          this.loadTemplates();
          this.selectedTemplateId = res.asset_id;
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
    };

    this.http.post<any>(`${environment.apiUrl}/api/template-merge/jobs`, payload)
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
          this.http.get<MergeJobStatus>(`${environment.apiUrl}/api/template-merge/jobs/${jobId}`)
        ),
        takeWhile((job) => !['completed', 'error'].includes(job.status), true)
      )
      .subscribe({
        next: (job) => {
          this.activeJob = job;
          if (job.status === 'completed') {
            this.completedJobs.unshift(job);
          }
        },
        error: () => {},
      });
  }

  // ── Download ──────────────────────────────────────────────────────────────

  downloadResult(job: MergeJobStatus): void {
    window.open(
      `${environment.apiUrl}/api/template-merge/jobs/${job.job_id}/download`,
      '_blank'
    );
  }

  // ── UI helpers ────────────────────────────────────────────────────────────

  get progressWidth(): string {
    return `${this.activeJob?.progress ?? 0}%`;
  }

  get isProcessing(): boolean {
    return !!this.activeJob && ['pending', 'processing'].includes(this.activeJob.status);
  }

  resetForm(): void {
    this.activeJob = null;
    this.submitError = '';
  }
}
