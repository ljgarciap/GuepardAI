import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { BrandService } from '../../services/brand.service';

@Component({
  selector: 'app-brand-manager',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './brand-manager.component.html',
  styleUrl: './brand-manager.component.css'
})
export class BrandManagerComponent implements OnInit {
  private brandService = inject(BrandService);

  brands: any[] = [];
  showCreateForm = false;
  editingId: number | null = null;
  
  newBrand = {
    name: '',
    about: '',
    coreValue: ''
  };

  selectedLogoFile: File | null = null;
  logoPreview: string | null = null;

  ngOnInit() {
    this.loadBrands();
  }

  loadBrands() {
    this.brandService.getBrands().subscribe({
      next: (res) => {
        this.brands = res;
      },
      error: (err) => console.error('Error loading brands:', err)
    });
  }

  editBrand(brand: any) {
    this.editingId = brand.id;
    this.newBrand = {
      name: brand.name,
      about: brand.about || '',
      coreValue: brand.core_value || ''
    };
    this.logoPreview = brand.logo_path ? 'http://localhost:8000/' + brand.logo_path : null;
    this.showCreateForm = true;
  }

  onLogoSelected(event: any) {
    const file = event.target.files[0];
    if (file) {
      this.selectedLogoFile = file;
      const reader = new FileReader();
      reader.onload = () => this.logoPreview = reader.result as string;
      reader.readAsDataURL(file);
    }
  }

  saveBrand() {
    if (!this.newBrand.name) return;

    const obs = this.editingId 
      ? this.brandService.updateBrand(this.editingId, this.newBrand.name, this.newBrand.about, this.newBrand.coreValue, this.selectedLogoFile || undefined)
      : this.brandService.createBrand(this.newBrand.name, this.newBrand.about, this.newBrand.coreValue, this.selectedLogoFile || undefined);

    obs.subscribe({
      next: (res) => {
        this.loadBrands();
        this.resetForm();
        this.showCreateForm = false;
      },
      error: (err) => alert('Error saving brand identity: ' + (err.error?.detail || err.message))
    });
  }

  resetForm() {
    this.newBrand = {
      name: '',
      about: '',
      coreValue: ''
    };
    this.editingId = null;
    this.selectedLogoFile = null;
    this.logoPreview = null;
  }
}
