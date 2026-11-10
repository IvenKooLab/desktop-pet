name: Pull request / 拉取请求
description: 提议改动 Comi Pet / Propose a change to Comi Pet
title: '[类型] 简短描述 / Short summary: '
labels: []
body:
  - type: markdown
    attributes:
      value: |
        提交前请先阅读 [CONTRIBUTING.md](../blob/main/CONTRIBUTING.md)。
        Before opening a pull request, please read the contributing guide.

        - 角色造型与已批准的 Comi v2 素材保持一致；
        - 运行时保持零第三方依赖；
        - 不上传任何本机私有内容或凭据。
  - type: dropdown
    id: kind
    attributes:
      label: 改动类型 / Change type
      options:
        - 修复 / Bug fix
        - 新动作或素材 / Action or asset
        - 运行时 / Runtime
        - 适配器 / Adapter
        - 文档 / Documentation
        - CI 与构建 / CI and packaging
    validations:
      required: true
  - type: textarea
    id: what
    attributes:
      label: 改了什么 / What changed
      description: 对照当前 main 说明具体差异，附相关 issue（如有）。
    validations:
      required: true
  - type: textarea
    id: verify
    attributes:
      label: 验证记录 / Verification
      description: 写明实际跑过的命令与结果；未实机验证的项目请如实标注。
      placeholder: |
        python3 -m unittest discover -s tests
        node adapters/dsh/self-test.mjs
        node adapters/dsh/web-test.mjs
        zsh tools/build_macos.sh
        build/ComiPet.app/Contents/MacOS/ComiPet --self-test
    validations:
      required: true
  - type: checkboxes
    id: checks
    attributes:
      label: 自检 / Checklist
      options:
        - label: 未改变角色造型，未逐帧独立缩放 / Character design and unified scale preserved
          required: true
        - label: 运行时仍为零第三方依赖 / Runtime still has no third-party dependencies
          required: true
        - label: 三端桥接语义（Python / Swift / DSH）如有改动已同步 / Bridge semantics kept in sync where applicable
          required: false
        - label: 中英文文档与 CHANGELOG 已同步 / Bilingual docs and CHANGELOG updated
          required: false
