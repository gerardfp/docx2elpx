/*!
 * eXeLearning v3.0.1 Example Style Script File
 * -----------------------
 * Author: Ignacio Gros
 * Project: eXeLearning.net
 *
 * This JavaScript file is part of a style for eXeLearning.
 * Licensed under Creative Commons Attribution-ShareAlike (CC BY-SA).
 *
 * Note: The style's config.xml contains additional information
 *       about materials (images, fonts, etc.) created by third parties
 *       and included in this style.
 */

var exampleStyle = {
    init: function () {
        // Common functions
        if (this.inIframe()) $('body').addClass('in-iframe');
        var togglers = '';
        if ($('.nav-buttons').length) {
            $('.nav-buttons').append('<div id="styleLogo"></div>');
        } else {""
            // If there are no nav-buttons, we put it in the body as a backup.
            $('body').prepend('<div id="styleLogo"></div>');
        }
        if ($('#siteFooterContent').length) {
         $('#siteFooterContent').append('<div class="centrat"><div id="boti"></div></div>');
        }

        var $cc = $("#packageLicense");
        $(".page-content").append('<div id="sau" class="centrat">');
        $("#sau").html($cc);

        var $h1s = $("h1");

        $.each($h1s, function(index, el) {
            if($(el).text().length < 2 || $(el).text() == '<br>') {
                $(el).hide();
                $(el).parent().hide();
            }
        });


        if (this.isLocalStorageAvailable()) {
            togglers =
                '\
                <button type="button" id="darkModeToggler" class="toggler" title="' +
                $exe_i18n.mode_toggler +
                '">\
                    <span>' +
                $exe_i18n.mode_toggler +
                '</span>\
                </button>\
            ';
        }
        if (!$('body').hasClass('exe-web-site')) {
            $('.package-header').prepend(togglers);
            // Dark mode
            exampleStyle.darkMode.init();
            return;
        }
        // Add menu and search bar togglers
        togglers +=
            '\
            <button type="button" id="siteNavToggler" class="toggler" title="' +
            $exe_i18n.menu +
            '">\
                <span>' +
            $exe_i18n.menu +
            '</span>\
            </button>\
            <button type="button" id="searchBarTogger" class="toggler" title="' +
            $exe_i18n.search +
            '">\
                <span>' +
            $exe_i18n.search +
            '</span>\
            </button>\
        ';
        $('#siteNav').before(togglers);
        // Check the current NAV status
        var url = window.location.href;
        url = url.split('?');
        if (url.length > 1) {
            if (url[1].indexOf('nav=false') != -1) {
                $('body').addClass('siteNav-off');
                exampleStyle.params('add');
            }
        }
        // Dark mode
        this.darkMode.init();
        // Menu toggler
        $('#siteNavToggler').on('click', function () {
            if (exampleStyle.isLowRes()) {
                $('#exe-client-search').hide();
                if ($('body').hasClass('siteNav-off')) {
                    $('body').removeClass('siteNav-off');
                } else {
                    if ($('#siteNav').isInViewport()) {
                        $('body').addClass('siteNav-off');
                        exampleStyle.params('add');
                    }
                }
                window.scroll(0, 0);
            } else {
                $('body').toggleClass('siteNav-off');
                exampleStyle.params(
                    $('body').hasClass('siteNav-off') ? 'add' : 'remove'
                );
            }
        });
        // Search bar toggler
        $('#searchBarTogger').on('click', function () {
            var bar = $('#exe-client-search');
            if (bar.is(':visible')) {
                bar.hide();
            } else {
                if (exampleStyle.isLowRes()) {
                    $('body').addClass('siteNav-off');
                }
                bar.show();
                $('#exe-client-search-text').focus();
                window.scroll(0, 0);
            }
        });
        // Search form
        this.searchForm();
    },
    isLocalStorageAvailable: function () {
        var x = '';
        try {
            localStorage.setItem(x, x);
            localStorage.removeItem(x);
            return true;
        } catch (e) {
            return false;
        }
    },
    darkMode: {
        init: function () {
            $("#darkModeToggler").on("click", function () {
                var active = 'off';
                if (!$("html").hasClass("exe-dark-mode")) active = 'on';
                exampleStyle.darkMode.setMode(active);
            });
        },
        setMode: function (active) {
            var dark = false;
            var darkMode = localStorage.getItem('exeDarkMode');
            if (darkMode && darkMode == 'on') {
                dark = true;
            }
            if (active) {
                if (active == 'off') {
                    dark = false;
                } else {
                    dark = true;
                }
            }
            if (dark) {
                localStorage.setItem('exeDarkMode', 'on');
                $("html").addClass("exe-dark-mode");
            } else {
                localStorage.removeItem('exeDarkMode');
                $("html").removeClass("exe-dark-mode");
            }
        }
    },
    inIframe: function () {
        try {
            return window.self !== window.top;
        } catch (e) {
            return true;
        }
    },
    searchForm: function () {
        $('#exe-client-search-text').attr('class', 'form-control');
    },
    isLowRes: function () {
        return $('#siteNav').css('float') == 'none';
    },
    param: function (e, act) {
        if (act == 'add') {
            var ref = e.href;
            var con = '?';
            if (ref.indexOf('.html?') != -1) con = '&';
            var param = 'nav=false';
            if (ref.indexOf(param) == -1) {
                ref += con + param;
                e.href = ref;
            }
        } else {
            // This will remove all params
            var ref = e.href;
            ref = ref.split('?');
            e.href = ref[0];
        }
    },
    params: function (act) {
        $('.nav-buttons a').each(function () {
            exampleStyle.param(this, act);
        });
    },
};
$(function () {
    exampleStyle.init();
});
exampleStyle.darkMode.setMode();
$.fn.isInViewport = function () {
    var elementTop = $(this).offset().top;
    var elementBottom = elementTop + $(this).outerHeight();
    var viewportTop = $(window).scrollTop();
    var viewportBottom = viewportTop + $(window).height();
    return elementBottom > viewportTop && elementTop < viewportBottom;
};
