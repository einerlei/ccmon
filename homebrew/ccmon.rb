class Ccmon < Formula
  include Language::Python::Virtualenv

  desc "Terminal monitor for Claude Code sessions and subagents"
  homepage "https://github.com/einerlei/ccmon"
  url "https://files.pythonhosted.org/packages/source/c/ccmon/ccmon-0.5.0.tar.gz"
  sha256 "PLACEHOLDER_SHA256"
  license "MIT"

  depends_on "python@3.12"

  def install
    venv = virtualenv_create(libexec, "python3")
    venv.pip_install "ccmon==#{version}"
    bin.install_symlink libexec/"bin/ccmon"
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/ccmon --version 2>&1", 1)
  end
end
