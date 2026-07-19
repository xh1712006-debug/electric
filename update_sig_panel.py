import re

with open('d:/project/dien-luc/templates/sheets/partials/_signature_panel.html', 'r', encoding='utf-8') as f:
    content = f.read()

new_content = '''<!-- TRẠNG THÁI CHỮ KÝ SỐ -->
<div class="bg-white rounded-xl shadow-sm border border-slate-100 p-6 mb-6" id="signature-panel">
    <h3 class="text-sm font-semibold text-slate-800 mb-6 uppercase tracking-wide">Quy trình Ký số & Phê duyệt</h3>
    
    <div x-data="{ 
            openModal: false, 
            sessionUrl: '', 
            currentRole: '',
            pin: '',
            signState: 'input', // input, loading, success
            pinError: false,
            initiateSign(role) {
                fetch('{% url 'initiate_signature' sheet.pk %}', {
                    method: 'POST',
                    headers: { 'X-CSRFToken': '{{ csrf_token }}', 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: 'role=' + role
                })
                .then(response => response.json())
                .then(data => {
                    if(data.success) {
                        this.sessionUrl = data.signing_url;
                        this.currentRole = data.role;
                        this.pin = '';
                        this.signState = 'input';
                        this.pinError = false;
                        this.openModal = true;
                    }
                });
            },
            verifyPin() {
                if (this.pin === '123456') {
                    this.pinError = false;
                    this.signState = 'loading';
                    setTimeout(() => {
                        this.signState = 'success';
                        setTimeout(() => {
                            this.$refs.signForm.requestSubmit();
                        }, 1000);
                    }, 2000); // fake loading 2s
                } else {
                    this.pinError = true;
                    this.pin = '';
                }
            }
        }">
        
        <!-- Timeline / Stepper -->
        <div class="relative pl-6 space-y-8 before:absolute before:inset-0 before:ml-[1.4rem] before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-slate-200 before:to-transparent">
            
            <!-- 1. Role Technician -->
            <div class="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
                <div class="flex items-center justify-center w-8 h-8 rounded-full border-4 border-white bg-slate-200 text-slate-500 shadow shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 z-10 {% if tech_sig %}bg-green-500 text-white{% endif %}">
                    <i class="fas fa-wrench text-xs"></i>
                </div>
                <div class="w-[calc(100%-3rem)] md:w-[calc(50%-2.5rem)] p-4 rounded-xl border shadow-sm {% if tech_sig %}border-green-200 bg-green-50/50{% else %}border-slate-200 bg-white{% endif %}">
                    <div class="flex items-center justify-between mb-1">
                        <h4 class="font-bold text-slate-800 text-sm">1. Kỹ thuật viên (Thực hiện)</h4>
                        {% if sheet.status == 'RECEIVED' and not tech_sig and perms.sheets.can_execute_sheet %}
                        <button @click="initiateSign('TECHNICIAN')" class="px-3 py-1 text-xs font-semibold bg-amber-500 text-white rounded hover:bg-amber-600 transition-colors shadow-sm">Ký số</button>
                        {% endif %}
                    </div>
                    {% if tech_sig %}
                        <p class="text-xs text-green-700 mt-2 font-medium"><i class="fas fa-check-circle mr-1"></i>Đã ký: {{ tech_sig.signer_name }}</p>
                        <p class="text-xs text-slate-500 mt-1"><i class="far fa-clock mr-1"></i>{{ tech_sig.signed_at|date:"d/m/Y H:i" }}</p>
                        <p class="text-[10px] text-slate-400 font-mono mt-1 break-all bg-white px-2 py-1 rounded border border-slate-100">Hash: {{ tech_sig.signature_hash }}</p>
                    {% else %}
                        <p class="text-xs text-slate-500 mt-2"><i class="fas fa-hourglass-half mr-1"></i>Đang chờ thao tác và ký số xác nhận.</p>
                    {% endif %}
                </div>
            </div>

            <!-- 2. Role Supervisor -->
            <div class="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
                <div class="flex items-center justify-center w-8 h-8 rounded-full border-4 border-white bg-slate-200 text-slate-500 shadow shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 z-10 {% if sup_sig %}bg-green-500 text-white{% endif %}">
                    <i class="fas fa-eye text-xs"></i>
                </div>
                <div class="w-[calc(100%-3rem)] md:w-[calc(50%-2.5rem)] p-4 rounded-xl border shadow-sm {% if sup_sig %}border-green-200 bg-green-50/50{% else %}border-slate-200 bg-white{% endif %}">
                    <div class="flex items-center justify-between mb-1">
                        <h4 class="font-bold text-slate-800 text-sm">2. Giám sát trạm (Xác nhận)</h4>
                        {% if sheet.status == 'RECEIVED' and tech_sig and not sup_sig and perms.sheets.can_supervise_sheet %}
                        <button @click="initiateSign('SUPERVISOR')" class="px-3 py-1 text-xs font-semibold bg-emerald-600 text-white rounded hover:bg-emerald-700 transition-colors shadow-sm">Ký số</button>
                        {% endif %}
                    </div>
                    {% if sup_sig %}
                        <p class="text-xs text-green-700 mt-2 font-medium"><i class="fas fa-check-circle mr-1"></i>Đã ký: {{ sup_sig.signer_name }}</p>
                        <p class="text-xs text-slate-500 mt-1"><i class="far fa-clock mr-1"></i>{{ sup_sig.signed_at|date:"d/m/Y H:i" }}</p>
                        <p class="text-[10px] text-slate-400 font-mono mt-1 break-all bg-white px-2 py-1 rounded border border-slate-100">Hash: {{ sup_sig.signature_hash }}</p>
                    {% else %}
                        <p class="text-xs text-slate-500 mt-2"><i class="fas fa-lock text-slate-300 mr-1"></i>Chờ Kỹ thuật viên hoàn tất trước.</p>
                    {% endif %}
                </div>
            </div>
            
            <!-- 3. Role A0/A1 -->
            <div class="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
                <div class="flex items-center justify-center w-8 h-8 rounded-full border-4 border-white bg-slate-200 text-slate-500 shadow shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 z-10 {% if a0_sig %}bg-blue-500 text-white{% endif %}">
                    <i class="fas fa-building text-xs"></i>
                </div>
                <div class="w-[calc(100%-3rem)] md:w-[calc(50%-2.5rem)] p-4 rounded-xl border shadow-sm {% if a0_sig %}border-blue-200 bg-blue-50/50{% else %}border-slate-200 bg-white{% endif %}">
                    <div class="flex items-center justify-between mb-1">
                        <h4 class="font-bold text-slate-800 text-sm">3. A0/A1 (Phê chuẩn)</h4>
                        {% if sheet.status == 'PENDING_REVIEW' and not a0_sig and perms.sheets.can_create_sheet %}
                        <button @click="initiateSign('A0_A1')" class="px-3 py-1 text-xs font-semibold bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors shadow-sm">Ký Duyệt</button>
                        {% endif %}
                    </div>
                    {% if a0_sig %}
                        <p class="text-xs text-blue-700 mt-2 font-medium"><i class="fas fa-check-circle mr-1"></i>Đã phê chuẩn: {{ a0_sig.signer_name }}</p>
                        <p class="text-xs text-slate-500 mt-1"><i class="far fa-clock mr-1"></i>{{ a0_sig.signed_at|date:"d/m/Y H:i" }}</p>
                        <p class="text-[10px] text-slate-400 font-mono mt-1 break-all bg-white px-2 py-1 rounded border border-slate-100">Hash: {{ a0_sig.signature_hash }}</p>
                    {% else %}
                        <p class="text-xs text-slate-500 mt-2"><i class="fas fa-lock text-slate-300 mr-1"></i>Chờ Giám sát trạm ký xác nhận trước.</p>
                    {% endif %}
                </div>
            </div>

        </div>

        <!-- SmartCA Mockup Modal -->
        <div x-show="openModal" class="fixed inset-0 z-50 overflow-y-auto flex items-center justify-center bg-slate-900/60 backdrop-blur-sm" style="display: none;" x-cloak>
            <div @click.away="if(signState==='input') openModal = false" class="bg-white rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden transform transition-all relative">
                
                <!-- Header -->
                <div class="bg-gradient-to-r from-red-600 to-red-700 px-6 py-4 flex items-center justify-between">
                    <div class="flex items-center gap-2">
                        <div class="w-8 h-8 bg-white rounded flex items-center justify-center">
                            <i class="fas fa-bolt text-red-600 text-lg"></i>
                        </div>
                        <h3 class="text-white font-bold text-lg">EVN SmartCA</h3>
                    </div>
                    <button x-show="signState==='input'" @click="openModal = false" class="text-white/80 hover:text-white"><i class="fas fa-times"></i></button>
                </div>

                <!-- Body -->
                <div class="p-6">
                    <!-- State: Input PIN -->
                    <div x-show="signState === 'input'" class="text-center">
                        <p class="text-slate-600 text-sm mb-4">Vui lòng nhập mã PIN ký số để xác nhận thao tác của bạn.</p>
                        <div class="flex justify-center gap-2 mb-2">
                            <!-- fake pin input visualization -->
                            <input type="password" x-model="pin" @keyup.enter="verifyPin" maxlength="6" class="tracking-[1em] text-center w-full text-2xl font-mono border-b-2 border-slate-300 focus:border-red-600 outline-none pb-1" placeholder="••••••">
                        </div>
                        <p x-show="pinError" class="text-xs text-red-500 mt-2 font-medium" style="display: none;">Mã PIN không đúng. Vui lòng thử lại (Gợi ý: 123456).</p>
                        <button @click="verifyPin" class="mt-6 w-full py-3 bg-red-600 hover:bg-red-700 text-white rounded-xl font-bold uppercase tracking-wide transition-colors shadow-lg shadow-red-200">
                            Xác thực
                        </button>
                        <p class="text-xs text-slate-400 mt-4"><i class="fas fa-shield-alt mr-1"></i> Chứng thư số được bảo mật bởi EVN CA</p>
                    </div>

                    <!-- State: Loading / Hashing -->
                    <div x-show="signState === 'loading'" class="text-center py-6" style="display: none;">
                        <div class="relative w-16 h-16 mx-auto mb-4">
                            <div class="absolute inset-0 border-4 border-slate-100 rounded-full"></div>
                            <div class="absolute inset-0 border-4 border-red-600 rounded-full border-t-transparent animate-spin"></div>
                            <i class="fas fa-fingerprint absolute inset-0 flex items-center justify-center text-xl text-red-600"></i>
                        </div>
                        <h4 class="font-bold text-slate-800">Đang ký số văn bản...</h4>
                        <p class="text-xs text-slate-500 mt-2">Đang khởi tạo mã Hash SHA-256...</p>
                        <div class="w-full bg-slate-100 h-1.5 mt-4 rounded-full overflow-hidden">
                            <div class="bg-red-600 h-full w-full animate-[progress_2s_ease-in-out]"></div>
                        </div>
                    </div>

                    <!-- State: Success -->
                    <div x-show="signState === 'success'" class="text-center py-6" style="display: none;">
                        <div class="w-16 h-16 mx-auto mb-4 bg-green-100 text-green-600 rounded-full flex items-center justify-center text-3xl animate-[bounce_0.5s]">
                            <i class="fas fa-check"></i>
                        </div>
                        <h4 class="font-bold text-slate-800 text-lg">Ký số Thành công!</h4>
                        <p class="text-xs text-slate-500 mt-2">Văn bản đã được gắn chứng thư số hợp lệ.</p>
                    </div>
                    
                    <!-- Hidden Form for HTMX Submission -->
                    <form x-ref="signForm" hx-post="{% url 'confirm_signature' sheet.pk %}" 
                          hx-target="#signature-panel" 
                          hx-swap="outerHTML"
                          @submit="setTimeout(() => { openModal = false; location.reload(); }, 300);">
                        {% csrf_token %}
                        <input type="hidden" name="role" x-model="currentRole">
                    </form>
                </div>
            </div>
        </div>
    </div>
</div>
'''

with open('d:/project/dien-luc/templates/sheets/partials/_signature_panel.html', 'w', encoding='utf-8') as f:
    f.write(new_content)
